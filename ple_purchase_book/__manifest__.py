{
    'name': 'Electronic Purchase Record',
    'version': '18.0.1.0.6',
    'website': 'https://www.sinetics.com.pe',
    'author': 'Sinetics',
    'category': 'Human Resources/Accounting',
    'summary': 'Generate your Electronic Purchase Record for PLE SUNAT',
    'description': """ 
The module provides the ability to generate detailed reports in Excel and TXT format for both national and non-domiciled purchases. These reports include comprehensive data on purchasing transactions, such as supplier details, billing information, payment data, and other relevant aspects.
""",
    'depends': [
        'ple_sale_book',
        'base_spot',
        'document_in_supplier_invoice',
        'l10n_pe_catalog'
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/account_tax_report_data.xml',
        'data/exoneration_nodomicilied_data.xml',
        'data/presumed_net_income_data.xml',
        'data/link_economic_data.xml',
        'data/service_taken_data.xml',
        'data/type_rent_data.xml',
        'data/account_function_data.xml',
        'views/ple_report_purchase_menus.xml',
        'views/ple_report_purchase_views.xml',
        'views/account_move_views.xml',
        'views/link_economic_views.xml',
        'views/res_country_views.xml',
        'sql/get_tax_purchase.sql'
    ],
    'post_init_hook': '_account_tax_hook',
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'Other proprietary',
    'currency': 'USD',
    'price': 460.00,
    'module_type': 'official'
}
