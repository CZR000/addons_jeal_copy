from odoo import fields, models, api


class LinkEconomic(models.Model):
    _name = 'link.economic'
    _description = 'Vínculo Contribuyente - Residente en el extranjero'

    code = fields.Char(
        string='Codigo', 
        required=True, 
        size=2
    )
    name = fields.Char(
        string='Nombre', 
        required=True
    )
    description = fields.Text(
        string='Descripcion'
    )
    law = fields.Char(
        string='Ley'
    )

    @api.constrains('code')
    def _constrains_codigo(self):
        for rec in self:
            if len(str(rec.code)) != 2:
                raise Warning('El campo código debe contener 2 dígitos.')