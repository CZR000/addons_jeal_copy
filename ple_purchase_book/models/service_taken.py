from odoo import fields, models, api


class ServiceTaken(models.Model):
    _name = 'service.taken'
    _description = 'Servicio Prestado'
    _rec_name = 'desctiption'

    code = fields.Char(
        string='Código', 
        required=True, 
        size=1
    )
    desctiption = fields.Char(
        string='Descripcion', 
        size=100
    )