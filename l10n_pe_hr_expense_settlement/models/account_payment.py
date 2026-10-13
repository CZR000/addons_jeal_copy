from odoo import models


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _l10n_pe_ensure_journal_entry(self):
        """Los anticipos y devoluciones deben quedar en la cuenta 14 al publicarse.
        Si el método de pago del diario no tiene cuenta de pagos/cobros pendientes,
        Odoo no genera el asiento hasta conciliar el extracto (en una caja chica,
        nunca): se registra directo contra la cuenta del banco o la caja."""
        for payment in self.filtered(lambda payment: not payment.outstanding_account_id):
            payment.outstanding_account_id = payment.journal_id.default_account_id
