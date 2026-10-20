import logging
from collections import defaultdict

from odoo import _, fields, models
from odoo.exceptions import UserError

from ..reports.report_inv_bal_0301 import InvBal31ReportExcel

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0301(models.Model):
    """Formato 3.1 (Balance General) del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_01(self):
        """Formato 3.1 - Balance General."""
        return self._generate_single('01')

    def _prepare_report_01(self):
        self.ensure_one()
        return InvBal31ReportExcel(self, self._get_data_01())

    # ------------------------------------------------------------------
    # DATA - Formato 3.1 Balance General
    # ------------------------------------------------------------------
    #
    # Las filas, sus nombres y sus importes salen del reporte contable
    # "Balance de situacion" de Odoo (Contabilidad > Reportes), al
    # `date_end`. Se mantiene la tabla de siempre:
    #   - Columna ACTIVO: primera linea principal del reporte (Activos).
    #   - Columna PASIVO Y PATRIMONIO: las demas lineas principales
    #     (Pasivos, Patrimonio, Pasivos + Patrimonio).
    #   - Cada grupo: seccion en mayusculas, sus lineas, "TOTAL <GRUPO>"
    #     y una fila en blanco, igual que antes.
    #   - Las lineas de tercer nivel o mas no se abren: se muestra la
    #     linea de segundo nivel con su importe (que ya las incluye).

    def _get_data_01(self):
        """Devuelve la estructura del Balance General (columnas ACTIVO y
        PASIVO Y PATRIMONIO) con los importes del Balance de situacion
        al `date_end`.

        Retorna dict con:
            'activo':  lista de filas (tipo, label, valor)
            'pasivo':  lista de filas (tipo, label, valor)
        Tipos de fila: 'section', 'line', 'total', 'blank'.
        """
        self.ensure_one()
        lines = self._get_balance_sheet_lines()

        by_id = {line['id']: line for line in lines}
        children = defaultdict(list)
        roots = []
        for line in lines:
            parent = line.get('parent_id')
            if parent and parent in by_id:
                children[parent].append(line)
            else:
                roots.append(line)

        if not roots:
            raise UserError(_(
                'El Balance de situación no devolvió líneas al %s.'
            ) % self.date_end.strftime('%d/%m/%Y'))

        def name(line):
            return line.get('name') or ''

        def add_root(root, rows):
            """Seccion principal con sus grupos y su total."""
            kids = children.get(root['id'])
            if not kids:
                rows.append(('total', name(root).upper(), self._report_line_value(root)))
                rows.append(('blank', '', None))
                return
            rows.append(('section', name(root).upper(), None))
            for child in kids:
                grandkids = children.get(child['id'])
                if grandkids:
                    rows.append(('section', name(child).upper(), None))
                    for grandkid in grandkids:
                        rows.append(('line', name(grandkid), self._report_line_value(grandkid)))
                    rows.append(('total', _('TOTAL %s') % name(child).upper(),
                                 self._report_line_value(child)))
                    rows.append(('blank', '', None))
                else:
                    rows.append(('line', name(child), self._report_line_value(child)))
            if rows[-1][0] != 'blank':
                rows.append(('blank', '', None))
            rows.append(('total', _('TOTAL %s') % name(root).upper(),
                         self._report_line_value(root)))
            rows.append(('blank', '', None))

        activo = []
        add_root(roots[0], activo)

        pasivo = []
        for root in roots[1:]:
            add_root(root, pasivo)

        # Sin fila en blanco al final de cada columna.
        for rows in (activo, pasivo):
            while rows and rows[-1][0] == 'blank':
                rows.pop()

        return {'activo': activo, 'pasivo': pasivo}

    def _get_balance_sheet_report(self):
        """Balance de situacion de Odoo; si existe una variante para el pais
        de la compania (p.ej. Peru), se usa esa."""
        root = self.env.ref('account_reports.balance_sheet', raise_if_not_found=False)
        if not root:
            raise UserError(_(
                'No se encontró el reporte "Balance de situación" '
                '(módulo account_reports).'
            ))
        country = self.company_id.account_fiscal_country_id
        if country:
            variant = self.env['account.report'].search([
                ('root_report_id', '=', root.id),
                ('country_id', '=', country.id),
            ], limit=1)
            if variant:
                return variant
        return root

    def _get_balance_sheet_lines(self):
        """Lineas del Balance de situacion al `date_end`, sin desplegar
        cuentas, en el orden del reporte. Solo las lineas propias del
        reporte (account.report.line)."""
        self.ensure_one()
        company = self.company_id
        report = self._get_balance_sheet_report().with_company(company).with_context(
            allowed_company_ids=[company.id],
        )
        fy_start = company.compute_fiscalyear_dates(self.date_end)['date_from']
        date_to = fields.Date.to_string(self.date_end)
        options = report.get_options(previous_options={
            'date': {
                'date_from': fields.Date.to_string(fy_start),
                'date_to': date_to,
                'filter': 'custom',
                'mode': 'single',
                'period_type': 'custom',
            },
            'comparison': {'filter': 'no_comparison', 'number_period': 1},
            'unfold_all': False,
            'unfolded_lines': [],
        })
        if (options.get('date') or {}).get('date_to') != date_to:
            raise UserError(_(
                'No se pudo calcular el Balance de situación al %s '
                '(el reporte devolvió la fecha %s).'
            ) % (self.date_end.strftime('%d/%m/%Y'),
                 (options.get('date') or {}).get('date_to') or '-'))

        result = []
        for line in report._get_lines(options):
            try:
                _markup, model, _res_id = report._parse_line_id(line['id'])[-1]
            except (KeyError, IndexError, ValueError):
                continue
            if model == 'account.report.line':
                result.append(line)
        return result

    @staticmethod
    def _report_line_value(line):
        """Importe de la primera columna de la linea del reporte."""
        columns = line.get('columns') or []
        if not columns:
            return 0.0
        try:
            return float(columns[0].get('no_format') or 0.0)
        except (TypeError, ValueError):
            return 0.0
