from odoo import api, models
import logging
_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    @api.model
    def create_dynamic_pe_templates(self):
        # Filtrar compañías peruanas
        companies = self.env['res.company'].search([('chart_template', '=', 'pe')])
        # Definir los datos de productos y sus impuestos
        templates_data = [
            {
                'name': 'VALOR CIF REFERENCIAL',
                'taxes': ['account_tax_cif', 'account_tax_igv_18_dua', 'account_tax_perc_dua'],
                'xml_id': 'product_template_valor_cif_ref'
            },
            {
                'name': 'Valor ref. - No domiciliado',
                'taxes': ['account_tax_valor_ref', 'account_tax_igv_18_cred_no_dom'],
                'xml_id': 'product_template_valor_ref_no_dom'
            }
        ]

        for company in companies:
            for template in templates_data:
                # Buscar los impuestos dinámicamente según la compañía
                tax_ids = []
                for tax_name in template['taxes']:
                    tax = self.env.ref(f'account.{company.id}_{tax_name}', raise_if_not_found=False)
                    if tax:
                        tax_ids.append(tax.id)
                    else:
                        # Registrar un log en lugar de interrumpir
                        _logger.warning(f"El impuesto {tax_name} no existe para la compañía {company.name} y no se incluirá.")

                # Crear o actualizar el producto solo si hay al menos un impuesto
                if tax_ids:
                    product_template = self.env['product.template'].search([
                        ('name', '=', template['name']),
                        ('company_id', '=', company.id)
                    ], limit=1)

                    if not product_template:
                        # Crear el producto
                        product_template = self.create({
                            'name': template['name'],
                            'purchase_ok': True,
                            'type': 'service',
                            'categ_id': self.env.ref('product.product_category_all').id,
                            'uom_id': self.env.ref('uom.product_uom_unit').id,
                            'uom_po_id': self.env.ref('uom.product_uom_unit').id,
                            'company_id': company.id,
                            'supplier_taxes_id': [(6, 0, tax_ids)]
                        })
                    else:
                        # Actualizar el producto existente
                        product_template.write({
                            'supplier_taxes_id': [(6, 0, tax_ids)]
                        })

                    # Crear la referencia XML si no existe
                    xml_id = f"{template['xml_id']}_{company.id}"
                    if not self.env['ir.model.data'].search([('name', '=', xml_id)]):
                        self.env['ir.model.data'].create({
                            'name': xml_id,
                            'module': 'ple_purchase_book',
                            'model': 'product.template',
                            'res_id': product_template.id,
                            'noupdate': True
                        })