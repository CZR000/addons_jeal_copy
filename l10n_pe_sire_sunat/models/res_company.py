from odoo import fields, models

class ResCompany(models.Model):
    _inherit = 'res.company'

    exceeds_1500_uit = fields.Boolean(
        string='Supera 1500 UIT', 
    )