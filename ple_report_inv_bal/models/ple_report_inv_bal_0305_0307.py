import logging
from datetime import datetime, time

import pytz

from odoo import models

from ..reports.report_inv_bal_0305_0307 import (
    InvBal35ReportExcel,
    InvBal36ReportExcel,
    InvBal37ReportExcel,
)

_logger = logging.getLogger(__name__)


# Tabla 5 SUNAT (tipo de existencia) segun el prefijo de la cuenta de
# valuacion de la categoria del producto. El formato 3.7 solo detalla las
# cuentas 20 (mercaderias) y 21 (productos terminados).
TABLA5_BY_ACCOUNT_PREFIX = {
    '20': '01',   # Mercaderias
    '21': '02',   # Productos terminados
}

COST_METHOD_LABELS = {
    'average': 'PROMEDIO PONDERADO',
    'fifo': 'PRIMERAS ENTRADAS, PRIMERAS SALIDAS (PEPS)',
    'standard': 'COSTO ESTÁNDAR',
}


class PleReportInvBalBook0305To0307(models.Model):
    """Formatos 3.5, 3.6 y 3.7 del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_05(self):
        """Formato 3.5 - Cuentas por cobrar diversas (cuenta 16)."""
        return self._generate_single('05')

    def _prepare_report_05(self):
        self.ensure_one()
        return InvBal35ReportExcel(self, self._get_data_05())

    def action_generate_06(self):
        """Formato 3.6 - Estimacion de cobranza dudosa (cuenta 19)."""
        return self._generate_single('06')

    def _prepare_report_06(self):
        self.ensure_one()
        return InvBal36ReportExcel(self, self._get_data_06())

    def action_generate_07(self):
        """Formato 3.7 - Mercaderias y productos terminados (20 y 21)."""
        return self._generate_single('07')

    def _prepare_report_07(self):
        self.ensure_one()
        return InvBal37ReportExcel(self, self._get_data_07())

    # ------------------------------------------------------------------
    # DATA - Formato 3.5 Cuentas por cobrar diversas (cuenta 16)
    # ------------------------------------------------------------------
    def _get_data_05(self):
        """Datos del formato 3.5 - Cuentas por cobrar diversas (cuenta 16)."""
        self.ensure_one()
        return self._get_open_items(['16'], date_source='invoice')

    # ------------------------------------------------------------------
    # DATA - Formato 3.6 Estimacion de cobranza dudosa (cuenta 19)
    # ------------------------------------------------------------------
    def _get_data_06(self):
        """Provisiones pendientes de la cuenta 19 al `date_end`, por deudor
        y documento. Las lineas sin tercero se muestran por asiento para
        no perder el numero de documento. El monto provisionado se muestra
        en positivo (la 19 tiene saldo natural acreedor)."""
        self.ensure_one()
        data = self._get_open_items(
            ['19'], date_source='invoice', split_no_partner=True,
        )
        for row in data['lines']:
            row['amount'] = -row['amount']
        data['total'] = -data['total']
        return data

    # ------------------------------------------------------------------
    # DATA - Formato 3.7 Mercaderias y productos terminados (cuentas 20 y 21)
    # ------------------------------------------------------------------
    def _get_data_07(self):
        """Existencias por producto al cierre de `date_end`, tomadas de la
        valorizacion de inventario de Odoo (stock.valuation.layer), igual
        que el reporte "Valoracion de inventario" a una fecha.

        Solo incluye productos cuya categoria tiene valoracion automatica
        (real_time) y cuenta de valuacion 20 o 21. Las categorias con
        valoracion manual no impactan la contabilidad y se excluyen.

        Retorna {'lines': [{code, existence_type, description, uom_code,
        quantity, unit_cost, total_cost}], 'total', 'method'}.
        """
        self.ensure_one()
        categories = self.env['product.category'].with_company(
            self.company_id
        ).search([])

        categ_info = {}
        for categ in categories:
            if categ.property_valuation != 'real_time':
                continue
            account = categ.property_stock_valuation_account_id
            prefix = (account.code or '')[:2] if account else ''
            if prefix in TABLA5_BY_ACCOUNT_PREFIX:
                categ_info[categ.id] = {
                    'existence_type': TABLA5_BY_ACCOUNT_PREFIX[prefix],
                    'cost_method': categ.property_cost_method,
                }
        if not categ_info:
            return {'lines': [], 'total': 0.0, 'method': ''}

        self.env.cr.execute("""
            SELECT svl.product_id, pt.categ_id,
                   COALESCE(SUM(svl.quantity), 0.0),
                   COALESCE(SUM(svl.value), 0.0)
              FROM stock_valuation_layer svl
              JOIN product_product pp ON pp.id = svl.product_id
              JOIN product_template pt ON pt.id = pp.product_tmpl_id
             WHERE svl.company_id = %(company)s
               AND svl.create_date <= %(date_limit)s
               AND pt.categ_id IN %(categs)s
             GROUP BY svl.product_id, pt.categ_id
        """, {
            'company': self.company_id.id,
            'date_limit': self._end_of_day_utc(self.date_end),
            'categs': tuple(categ_info),
        })
        rows_sql = [
            (product_id, categ_id, float(qty or 0.0), float(value or 0.0))
            for product_id, categ_id, qty, value in self.env.cr.fetchall()
            if abs(float(qty or 0.0)) > 1e-6 or abs(float(value or 0.0)) >= 0.005
        ]
        if not rows_sql:
            return {'lines': [], 'total': 0.0, 'method': ''}

        products = self.env['product.product'].with_context(
            active_test=False,
        ).browse([r[0] for r in rows_sql])
        product_by_id = {p.id: p for p in products}

        lines = []
        methods = set()
        for product_id, categ_id, qty, value in rows_sql:
            product = product_by_id[product_id]
            info = categ_info[categ_id]
            methods.add(info['cost_method'])
            uom = product.uom_id
            lines.append({
                'code': product.default_code or '',
                'existence_type': info['existence_type'],
                'description': product.name or '',
                'uom_code': getattr(uom, 'l10n_pe_edi_measure_unit_code', False)
                            or uom.name or '',
                'quantity': qty,
                'unit_cost': value / qty if abs(qty) > 1e-6 else 0.0,
                'total_cost': value,
            })

        lines.sort(key=lambda r: (r['code'] or '~', r['description'].upper()))
        method = ' / '.join(
            COST_METHOD_LABELS.get(m, (m or '').upper()) for m in sorted(methods)
        )
        return {
            'lines': lines,
            'total': sum(r['total_cost'] for r in lines),
            'method': method,
        }

    # ------------------------------------------------------------------
    # Helpers del grupo (solo los usan estos formatos)
    # ------------------------------------------------------------------
    def _end_of_day_utc(self, day):
        """Ultimo instante de `day` en la zona horaria del usuario,
        convertido a UTC naive (como se guarda create_date)."""
        tz = pytz.timezone(self.env.user.tz or 'America/Lima')
        local_end = tz.localize(datetime.combine(day, time.max))
        return local_end.astimezone(pytz.utc).replace(tzinfo=None)
