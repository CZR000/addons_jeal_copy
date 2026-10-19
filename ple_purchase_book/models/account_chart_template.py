from odoo import api, models,_
from odoo.addons.account.models.chart_template import template
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)


class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('pe', 'account.tax.group')
    def _get_pe_ple_purchase_book_group_tax(self):
        try:
            tax_groups = self._parse_csv('pe', 'account.tax.group', module='ple_purchase_book')
            return tax_groups
        except Exception as e:
            _logger.error(f"Error al parsear grupos de impuestos: {e}")
            return []

    @template('pe', 'account.tax')
    def _get_pe_ple_purchase_book_tax(self):
        try:
            taxes = self._parse_csv('pe', 'account.tax', module='ple_purchase_book')
            return taxes
        except Exception as e:
            _logger.error(f"Error al parsear impuestos: {e}")
            return []
    
    @api.model
    def ple_purchase_book_post_init(self):
        try:
            all_companies = self.env['res.company'].search([('chart_template', '=', 'pe')])
            for company in all_companies:

                existing_taxes = self.env['account.tax'].search([
                    ('company_id', '=', company.id),
                    ('name', 'in', [
                        'Valor Ref', '18% IGV - DUA', 'CIF', 
                        'IGV 18% CREDITO - NO DOMICILIADO', 'PERCEPCION DUA',
                        'ADVALOREM', 'IGV 18% NO DOMICILIADO', '30% RET NO DOMICILIADO'
                    ])
                ])
                if existing_taxes:
                    continue

                # Búsqueda de cuentas
                account_codes = [
                    '4011500', '4011300', '1674000', 
                    '4011200', '6419000', '4017400'
                ]
                
                # Verificar si todas las cuentas existen
                existing_accounts = self.env['account.account'].search([
                    ('code', 'in', account_codes),
                    ('company_ids', 'in', company.id)
                ])
                
                # Si se encuentran todas las cuentas, cargar los datos
                if len(existing_accounts) == len(account_codes):
                    Template = self.with_company(company)
                    Template._load_data({
                        'account.tax.group': self._get_pe_ple_purchase_book_group_tax(),
                        'account.tax': self._get_pe_ple_purchase_book_tax()
                    })
                else:
                    # Log de cuentas no encontradas
                    missing_accounts = set(account_codes) - set(existing_accounts.mapped('code'))
                    _logger.warning(f"Cuentas no encontradas para la compañía {company.name}: {missing_accounts}")
                    # Continúa sin cargar los datos para esta compañía
                    continue
            
            return True
        except Exception as e:
            _logger.error(f"Error en la inicialización de impuestos: {e}")
            raise UserError(_("Error al cargar datos de impuestos: %s") % str(e))