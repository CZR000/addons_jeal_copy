from odoo import api, models


class AccountJournals(models.Model):
    _inherit = 'account.journal'

    # overriding the @api.constrains (check_use_document) of the l10n_latam_invoice_document module
    @api.constrains('l10n_latam_use_documents')
    def check_use_document(self):
        pass

    @api.model
    def automated_creation(self):
        temp = self.env['account.journal'].search([('code', '=', '1662'),('company_id','=',self.env.company.id)], limit=1)
        account_id = self.env['account.account'].search([('code', '=', '6419000'),('company_ids', 'in',self.env.company.id)],limit=1)


        if temp and temp.company_id not in account_id.company_ids:
            return
        
        args = {
            'name': 'Formulario 1662',
            'type': 'purchase',
            'l10n_latam_use_documents': 0,
            'ple_no_include': 0,
            'ple_journal_correlative': 'M',
            'default_account_id': account_id.id,
            'refund_sequence': 1,
            'code': 1662,
        }

        if temp:
            temp.write(args)

        else:
            self.env['account.journal'].create(args)