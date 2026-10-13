from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    expense_analytic_distribution = fields.Json(
        string='Centro de costos',
        groups='hr.group_hr_user',
        help='Distribución analítica que se propone automáticamente en los gastos '
             'de este empleado.',
    )
    # Requerido por el widget analytic_distribution (ver analytic.mixin).
    analytic_precision = fields.Integer(
        store=False,
        default=lambda self: self.env['decimal.precision'].precision_get('Percentage Analytic'),
    )
