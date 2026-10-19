from pytz import timezone
from datetime import datetime

from odoo.tests.common import tagged
from odoo.tests.common import TransactionCase
from lxml import etree


@tagged('post_install', '-at_install')
class TestPlePurchaseBook(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.frozen_today = datetime(year=2024, month=5, day=31, hour=0, minute=0, second=0, tzinfo=timezone('utc'))

        cls.company_data = cls.env['res.company'].create({
            'name':'Company Peruvian',
            'vat': "20557912879",
            'country_id': cls.env.ref('base.pe').id,
            'ple_type_contributor': 'CUO',
        })
        
        cls.tax_group = cls.env['account.tax.group'].create({
            'name': "IGV",
            'l10n_pe_edi_code': "IGV",
        })

        cls.tax_18 = cls.env['account.tax'].create({
            'name': 'tax_18',
            'amount_type': 'percent',
            'amount': 18,
            'l10n_pe_edi_tax_code': '1000',
            'l10n_pe_edi_unece_category': 'S',
            'type_tax_use': 'sale',
            'tax_group_id': cls.tax_group.id,
        })

        cls.product = cls.env['product.product'].create({
            'name': 'product_ple',
            'uom_po_id': cls.env.ref('uom.product_uom_kgm').id,
            'uom_id': cls.env.ref('uom.product_uom_kgm').id,
            'lst_price': 1000.0,
        })
        
        cls.partner_a = cls.env['res.partner'].create({
            'name':'Comperuvian',
            'vat': '20462509236',
            'l10n_latam_identification_type_id': cls.env.ref('l10n_pe.it_RUC').id,
            'country_id': cls.env.ref('base.pe').id,
        })        
        
        cls.time_name = datetime.now().strftime('%H%M%S')
        
        cls.currency_data = cls.env['res.currency'].search([('name','=','PEN')])
        
    def setUp(self):
        super(TestPlePurchaseBook, self).setUp()
            
        # Crea una factura inical para el test
        self.move = self.env['account.move'].create({
            'name': 'F FFI-%s1' % self.time_name,
            'move_type': 'in_invoice',
            'partner_id': self.partner_a.id,
            'invoice_date': '2024-05-31',
            'date': '2024-05-31',
            'currency_id': self.currency_data.id,
            'exchange_rate': 1.000000,
            'origin_l10n_latam_document_type_id': self.env.ref('l10n_pe.document_type01').id,
            'l10n_latam_document_type_id': self.env.ref('l10n_pe.document_type01').id,
            'invoice_line_ids': [(0, 0, {
                'product_id': self.product.id,
                'product_uom_id': self.env.ref('uom.product_uom_kgm').id,
                'price_unit': 2000.0,
                'quantity': 5,
                'tax_ids': [(6, 0, self.tax_18.ids)],
            })],
        })
        
    def test_module_installed(self):
        # Verifica que el módulo está instalado
        installed_modules = self.env['ir.module.module'].search([('state', '=', 'installed')])
        module_names = installed_modules.mapped('name')
        self.assertIn('ple_purchase_book', module_names, 'El módulo no está instalado correctamente')
        
        
    def test_div_exists_in_view(self):
        
        # Accede a la vista donde se crear el div
        view = self.env.ref('account_exchange_currency.account_move_view_form_inherit_account_exchange_currency')
        tree = etree.fromstring(view.arch)

        div_name = 'exchange_rate_div'
        div_xpath = ".//div[@name='{}']".format(div_name)
        div_elements = tree.xpath(div_xpath)
        
        # Comprueba si existe el div con el nombre especificado
        self.assertTrue(div_elements, "El div con name='{}' no existe en la vista".format(div_name))

    def test_ple_purchase_book(self):
    
        self.move.action_post()

        ple_purchase_book = self.env['ple.report.purchase'].create({
            'date_start': '2023-01-01',
            'date_end': '2023-01-31',
            'company_id': self.company_data.id,
            'state_send': '1',
        })

        ple_purchase_book.action_generate_excel()

        self.assertTrue(ple_purchase_book.txt_binary_8_1)
        self.assertTrue(ple_purchase_book.xls_binary_8_1)
        self.assertTrue(ple_purchase_book.txt_binary_8_2)
        self.assertTrue(ple_purchase_book.xls_binary_8_2)
        
    def test_action_rollback(self):
        
        self.move.action_post()
        
        ple_purchase_book = self.env['ple.report.purchase'].create({
            'date_start': '2023-01-01',
            'date_end': '2023-01-31',
            'company_id': self.company_data.id,
            'state_send': '1',
        })
        
        ple_purchase_book.action_generate_excel()
        
        ple_purchase_book.action_rollback()
        
        self.assertRecordValues(self.move, [{'ple_its_declared': False}])
        
        self.assertFalse(ple_purchase_book.txt_binary_8_1)
        self.assertFalse(ple_purchase_book.xls_binary_8_1)
        self.assertFalse(ple_purchase_book.txt_binary_8_2)
        self.assertFalse(ple_purchase_book.xls_binary_8_2)
        
        
    def test_action_close(self):
         
        self.move.action_post()
        
        ple_purchase_book = self.env['ple.report.purchase'].create({
            'date_start': '2023-01-01',
            'date_end': '2023-01-31',
            'company_id': self.company_data.id,
            'state_send': '1',
        })
        
        ple_purchase_book.action_generate_excel()
        
        ple_purchase_book.action_close()
        
        self.assertRecordValues(self.move, [{'ple_its_declared': False}])
        
        self.assertTrue(ple_purchase_book.txt_binary_8_1)
        self.assertTrue(ple_purchase_book.xls_binary_8_1)
        self.assertTrue(ple_purchase_book.txt_binary_8_2)
        self.assertTrue(ple_purchase_book.xls_binary_8_2)