from odoo import api, models


class AccountTax(models.Model):
    _inherit = "account.tax"
        
    @api.model
    def _link_tags_ids(self):

        def generate_tag_id(name):
            return self.env['account.account.tag'].search([('name', '=', '%s' % name)], limit=1)

        def set_tag_ids(account_tax, first, second):
            tags = []
            if first and account_tax.repartition_type == 'base':
                tags.append((4, generate_tag_id(first).id))
            if second and account_tax.repartition_type == 'tax':
                tags.append((4, generate_tag_id(second).id))
            account_tax.write({'tag_ids': [(5, 0, 0)] + tags}) 

        type_acc = ['igv_18_dua', 'igv_18_cred_no_dom', 'igv_18_no_dom']
        tags_invoices = ['+P_BASE_GDG', '+P_TAX_GDG', '+P_BASE_NG']
        tags_invoices_corrective = ['-P_BASE_GDG', '-P_TAX_GDG', '-P_BASE_NG']
        
        companies = self.env['res.company'].search([('chart_template', '=', 'pe')])
        for company in companies:
            for rec in type_acc:
                try:
                    account = self.env.ref('account.%s_account_tax_%s' % (company.id,rec)) 
                    if rec == 'igv_18_dua':
                        for acc_tax in account.invoice_repartition_line_ids:
                            set_tag_ids(acc_tax, tags_invoices[0], tags_invoices[1])
                        for acc_tax in account.refund_repartition_line_ids:
                            set_tag_ids(acc_tax, tags_invoices_corrective[0], tags_invoices_corrective[1])
                    elif rec == 'igv_18_cred_no_dom':
                        for acc_tax in account.invoice_repartition_line_ids:
                            set_tag_ids(acc_tax, tags_invoices[0], tags_invoices[1])
                        for acc_tax in account.refund_repartition_line_ids:
                            set_tag_ids(acc_tax, tags_invoices_corrective[0], tags_invoices_corrective[1])
                    elif rec == 'igv_18_no_dom':
                        for acc_tax in account.invoice_repartition_line_ids:
                            set_tag_ids(acc_tax, tags_invoices[2], False)
                        for acc_tax in account.refund_repartition_line_ids:
                            set_tag_ids(acc_tax, tags_invoices_corrective[2], False)
                except:
                    pass
        
