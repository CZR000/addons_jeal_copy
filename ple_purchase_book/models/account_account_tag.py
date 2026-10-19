from odoo import api, models


class AccountTax(models.Model):
    _inherit = 'account.account.tag'

    @api.model
    def automated_links(self):
        tags = {}
        tax = {}
        lines = self.env['account.tax.repartition.line']
        comp_id = min(self.env['res.company'].search([]).ids)
        companies = self.env['res.company'].search([('chart_template', '=', 'pe')])

        if not comp_id:
            return

        # invoice
        tags['+P_BASE_GDG'] = self.env['account.account.tag'].search([('name', '=', '+P_BASE_GDG')], limit=1)
        tags['+P_TAX_GDG'] = self.env['account.account.tag'].search([('name', '=', '+P_TAX_GDG')], limit=1)
        tags['+P_BASE_NG'] = self.env['account.account.tag'].search([('name', '=', '+P_BASE_NG')], limit=1)
        tags['+P_BASE_GDM'] = self.env['account.account.tag'].search([('name', '=', '+P_BASE_GDM')], limit=1)
        tags['+P_TAX_GDM'] = self.env['account.account.tag'].search([('name', '=', '+P_TAX_GDM')], limit=1)
        tags['+P_BASE_GDNG'] = self.env['account.account.tag'].search([('name', '=', '+P_BASE_GDNG')], limit=1)
        tags['+P_TAX_GDNG'] = self.env['account.account.tag'].search([('name', '=', '+P_TAX_GDNG')], limit=1)

        # refund
        tags['-P_BASE_GDG'] = self.env['account.account.tag'].search([('name', '=', '-P_BASE_GDG')], limit=1)
        tags['-P_TAX_GDG'] = self.env['account.account.tag'].search([('name', '=', '-P_TAX_GDG')], limit=1)
        tags['-P_BASE_NG'] = self.env['account.account.tag'].search([('name', '=', '-P_BASE_NG')], limit=1)
        tags['-P_BASE_GDM'] = self.env['account.account.tag'].search([('name', '=', '-P_BASE_GDM')], limit=1)
        tags['-P_TAX_GDM'] = self.env['account.account.tag'].search([('name', '=', '-P_TAX_GDM')], limit=1)
        tags['-P_BASE_GDNG'] = self.env['account.account.tag'].search([('name', '=', '-P_BASE_GDNG')], limit=1)
        tags['-P_TAX_GDNG'] = self.env['account.account.tag'].search([('name', '=', '-P_TAX_GDNG')], limit=1)

        # tax
        for company in companies:
            # 18% 
            tax['18%'] = self.env.ref('account.%s_purchase_tax_igv_18' % (company.id), raise_if_not_found=False)
            if tax['18%']:
                lines.search([
                    ('id', 'in', tax['18%'].invoice_repartition_line_ids.ids), 
                    ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['+P_BASE_GDG'].ids})
                lines.search([('id', 'in', tax['18%'].invoice_repartition_line_ids.ids), ('repartition_type', '=', 'tax')],
                        limit=1
                        ).sudo().write({'tag_ids': tags['+P_TAX_GDG'].ids})
                
                
                lines.search([('id', 'in', tax['18%'].refund_repartition_line_ids.ids), ('repartition_type', '=', 'base')],
                        limit=1
                        ).sudo().write({'tag_ids': tags['-P_BASE_GDG'].ids})
                lines.search([('id', 'in', tax['18%'].refund_repartition_line_ids.ids), ('repartition_type', '=', 'tax')],
                        limit=1
                        ).sudo().write({'tag_ids': tags['-P_TAX_GDG'].ids})
            
            # 18% TTC 
            tax['18% (Included in price)'] = self.env.ref('account.%s_purchase_tax_igv_18_included' % (company.id), raise_if_not_found=False)
            if tax['18% (Included in price)']:
                lines.search(
                    [('id', 'in', tax['18% (Included in price)'].invoice_repartition_line_ids.ids),
                    ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['+P_BASE_GDG'].ids})
                lines.search(
                    [('id', 'in', tax['18% (Included in price)'].invoice_repartition_line_ids.ids),
                    ('repartition_type', '=', 'tax')], limit=1
                ).sudo().write({'tag_ids': tags['+P_TAX_GDG'].ids})
                lines.search(
                    [('id', 'in', tax['18% (Included in price)'].refund_repartition_line_ids.ids),
                    ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['-P_BASE_GDG'].ids})
                lines.search(
                    [('id', 'in', tax['18% (Included in price)'].refund_repartition_line_ids.ids),
                    ('repartition_type', '=', 'tax')], limit=1
                ).sudo().write({'tag_ids': tags['-P_TAX_GDG'].ids})
            
            # 0% Exo
            tax['0% Exonerated'] = self.env.ref('account.%s_purchase_tax_exo' % (company.id), raise_if_not_found=False)
            if tax['0% Exonerated']:
                lines.search(
                [('id', 'in', tax['0% Exonerated'].invoice_repartition_line_ids.ids), ('repartition_type', '=', 'base')],
                limit=1
                ).sudo().write({'tag_ids': tags['+P_BASE_NG'].ids})
                
                lines.search(
                [('id', 'in', tax['0% Exonerated'].refund_repartition_line_ids.ids), ('repartition_type', '=', 'base')],
                limit=1
                ).sudo().write({'tag_ids': tags['-P_BASE_NG'].ids})
            
            # 0% Una
            tax['0% Unaffected'] = self.env.ref('account.%s_purchase_tax_ina' % (company.id), raise_if_not_found=False)
            if tax['0% Unaffected']:
                lines.search(
                [('id', 'in', tax['0% Unaffected'].invoice_repartition_line_ids.ids), ('repartition_type', '=', 'base')],
                limit=1
                ).sudo().write({'tag_ids': tags['+P_BASE_NG'].ids})
                lines.search(
                [('id', 'in', tax['0% Unaffected'].refund_repartition_line_ids.ids), ('repartition_type', '=', 'base')],
                limit=1
                ).sudo().write({'tag_ids': tags['-P_BASE_NG'].ids})
            
            # 0%
            tax['0% Free'] = self.env.ref('account.%s_purchase_tax_gra' % (company.id), raise_if_not_found=False)
            if tax['0% Free']:
                lines.search(
                [('id', 'in', tax['0% Free'].invoice_repartition_line_ids.ids), ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['+P_BASE_NG'].ids})
                lines.search(
                [('id', 'in', tax['0% Free'].refund_repartition_line_ids.ids), ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['-P_BASE_NG'].ids})
            
            # 18% Levied and Not Taxed
            tax['18% Levied and Not Taxed'] = self.env.ref('account.%s_purchase_tax_igv_18g_ng' % (company.id), raise_if_not_found=False)
            if tax['18% Levied and Not Taxed']:
                lines.search([('id', 'in', tax['18% Levied and Not Taxed'].invoice_repartition_line_ids.ids), ('repartition_type', '=', 'base')],
                        limit=1
                        ).sudo().write({'tag_ids': tags['+P_BASE_GDNG'].ids})
                lines.search([('id', 'in', tax['18% Levied and Not Taxed'].invoice_repartition_line_ids.ids), ('repartition_type', '=', 'tax')],
                        limit=1
                        ).sudo().write({'tag_ids': tags['+P_TAX_GDNG'].ids})
                
                lines.search(
                [('id', 'in', tax['18% Levied and Not Taxed'].refund_repartition_line_ids.ids),
                ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['-P_BASE_GDNG'].ids})
                lines.search(
                    [('id', 'in', tax['18% Levied and Not Taxed'].refund_repartition_line_ids.ids),
                    ('repartition_type', '=', 'tax')], limit=1
                ).sudo().write({'tag_ids': tags['-P_TAX_GDNG'].ids})

            # 18% Not Levied
            tax['18% Not Levied'] = self.env.ref('account.%s_purchase_tax_igv_18_ng' % (company.id), raise_if_not_found=False)
            
            if tax['18% Not Levied']:
                lines.search(
                [('id', 'in', tax['18% Not Levied'].invoice_repartition_line_ids.ids),
                ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['+P_BASE_GDM'].ids})
                lines.search(
                    [('id', 'in', tax['18% Not Levied'].invoice_repartition_line_ids.ids),
                    ('repartition_type', '=', 'tax')], limit=1
                ).sudo().write({'tag_ids': tags['+P_TAX_GDM'].ids})
                
                lines.search(
                [('id', 'in', tax['18% Not Levied'].refund_repartition_line_ids.ids),
                ('repartition_type', '=', 'base')], limit=1
                ).sudo().write({'tag_ids': tags['-P_BASE_GDM'].ids})
                lines.search(
                    [('id', 'in', tax['18% Not Levied'].refund_repartition_line_ids.ids),
                    ('repartition_type', '=', 'tax')], limit=1
                ).sudo().write({'tag_ids': tags['-P_TAX_GDM'].ids})
