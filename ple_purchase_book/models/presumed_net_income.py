from odoo import api, fields, models


class PresumedNetIncome(models.Model):
    _name = 'presumed.net.income'
    _description = 'Renta Neta Presunta (Art. 48 LIR)'
    _order = 'code'
    _rec_names_search = ['name', 'code']

    code = fields.Char(
        string='Código',
        required=True,
        size=2
    )
    name = fields.Char(
        string='Actividad',
        required=True
    )
    percentage = fields.Float(
        string='Porcentaje (%)',
        digits=(5, 2),
        required=True,
        help='Porcentaje de renta neta presunta sobre los ingresos brutos, '
             'según el Art. 48 de la Ley del Impuesto a la Renta.'
    )
    base = fields.Char(
        string='Base',
        help='Base sobre la que se aplica el porcentaje presunto '
             '(p. ej. ingresos brutos o primas).'
    )

    @api.depends('name', 'percentage')
    def _compute_display_name(self):
        for record in self:
            # 7.00 -> '7', 2.50 -> '2.5'
            rate = ('%.2f' % record.percentage).rstrip('0').rstrip('.')
            record.display_name = '%s (%s%%)' % (record.name or '', rate)
