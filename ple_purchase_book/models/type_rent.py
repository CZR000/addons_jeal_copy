from odoo import fields, models


class TypeRent(models.Model):
    _name = 'type.rent'
    _description = 'Tipo de Renta'

    code = fields.Char(
        string='Codigo', 
        size=2, 
        required=True
    )
    name = fields.Text(
        string='Nombre', 
        required=True
    )
    description = fields.Text(
        string='Descipcion'
    )
    law = fields.Char(
        string='Ley', 
        size=100
    )
    ocde = fields.Char(
        string='OCDE', 
        size=8
    )