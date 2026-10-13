from odoo import fields, models


# Tabla 7 SUNAT - Tipo de intangible (formato 3.9).
TABLA7_INTANGIBLE_TYPES = [
    ('01', '01 - Intangible adquirido'),
    ('02', '02 - Intangible en etapa de investigación'),
    ('03', '03 - Intangible en etapa de desarrollo'),
]


class AccountAccount(models.Model):
    _inherit = 'account.account'

    l10n_pe_intangible_type = fields.Selection(
        TABLA7_INTANGIBLE_TYPES,
        string='Tipo de intangible (Tabla 7)',
        help='Tipo de intangible SUNAT (Tabla 7) que se informa en el '
             'formato 3.9 del Libro de Inventarios y Balances. Aplica a '
             'las cuentas 34 (Intangibles). Si se deja vacío se informa '
             '01 - Intangible adquirido.',
    )