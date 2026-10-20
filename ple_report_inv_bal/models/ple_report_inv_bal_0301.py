import logging
from collections import defaultdict

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..reports.report_inv_bal_0301 import InvBal31ReportExcel

_logger = logging.getLogger(__name__)

# Sangria por nivel de jerarquia en las etiquetas del Excel.
INDENT = '   '


class PleReportInvBalBook0301(models.Model):
    """Formato 3.1 (Balance General) del Libro de Inventarios y Balances.

    Las filas y los importes salen del reporte contable "Balance de
    situacion" de Odoo (account_reports), con las mismas lineas y los
    mismos calculos que se ven en Contabilidad > Reportes. Solo se cambia
    la presentacion: el layout de dos columnas del formato (ACTIVO a la
    izquierda, PASIVO Y PATRIMONIO a la derecha).
    """

    _inherit = 'ple.report.inv.bal.book'

    balance_report_id = fields.Many2one(
        'account.report', string='Balance de situación',
        compute='_compute_balance_report_id', store=True, readonly=False,
        help='Reporte contable del que se toman las filas y los importes '
             'del Formato 3.1. Por defecto, el Balance de situación de Odoo '
             '(o su variante para el país de la compañía).',
    )

    @api.depends('company_id')
    def _compute_balance_report_id(self):
        root = self.env.ref('account_reports.balance_sheet', raise_if_not_found=False)
        Report = self.env['account.report']
        for rec in self:
            if not root:
                rec.balance_report_id = False
                continue
            country = (rec.company_id or self.env.company).account_fiscal_country_id
            variant = Report.search([
                ('root_report_id', '=', root.id),
                ('country_id', '=', country.id),
            ], limit=1) if country else Report
            rec.balance_report_id = variant or root

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
    def _get_data_01(self):
        """Estructura del Balance General al `date_end`, tomada del reporte
        Balance de situacion.

        La primera linea raiz del reporte (Activos) va a la columna ACTIVO;
        las demas (Pasivos, Patrimonio, Pasivo + Patrimonio) a la columna
        PASIVO Y PATRIMONIO.

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
                'El reporte "%s" no devolvió líneas para el %s.'
            ) % (self.balance_report_id.display_name,
                 self.date_end.strftime('%d/%m/%Y')))

        def walk(line, depth, rows):
            name = line.get('name') or ''
            value = self._report_line_value(line)
            kids = children.get(line['id'])
            if kids:
                # Encabezado de grupo, sus lineas y el total del grupo.
                rows.append(('section', INDENT * depth + name, None))
                for kid in kids:
                    walk(kid, depth + 1, rows)
                rows.append(('total', INDENT * depth + _('TOTAL %s') % name.upper(), value))
            else:
                rows.append(('total' if depth == 0 else 'line', INDENT * depth + name, value))

        activo = []
        walk(roots[0], 0, activo)

        pasivo = []
        for root in roots[1:]:
            if pasivo:
                pasivo.append(('blank', '', None))
            walk(root, 0, pasivo)

        return {'activo': activo, 'pasivo': pasivo}

    def _get_balance_sheet_lines(self):
        """Lineas del Balance de situacion al `date_end`, sin desplegar
        cuentas. Solo se devuelven las lineas propias del reporte
        (account.report.line), en el orden del reporte."""
        self.ensure_one()
        if not self.balance_report_id:
            raise UserError(_(
                'Indique el reporte "Balance de situación" del que se toman '
                'los datos del Formato 3.1.'
            ))

        company = self.company_id
        report = self.balance_report_id.with_company(company).with_context(
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
        value = columns[0].get('no_format')
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0
