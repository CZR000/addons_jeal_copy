from odoo import fields, models


class ResCountry(models.Model):
    _inherit = 'res.country'

    l10n_pe_sunat_code = fields.Char(
        string='Código (Tabla 35 SUNAT)',
        help='Este código se completará en el libro electrónico de No domiciliados cada vez que una factura, tenga un proveedor asociado con este país.'
    )