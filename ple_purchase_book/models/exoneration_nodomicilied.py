from odoo import fields, models


class ExonerationNodomicilied(models.Model):
    _name = 'exoneration.nodomicilied'
    _description = 'Exoneración no Domiciliado'

    code = fields.Integer(
        string='Código',
        required=True
    )
    name = fields.Text(
        string='Nombre',
        required=True
    )
    description = fields.Text(
        string='Descripcion'
    )

