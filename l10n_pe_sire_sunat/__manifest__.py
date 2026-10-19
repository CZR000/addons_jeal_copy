{
    'name': 'Format SIRE SUNAT (Book Sale and Purchase)',
    'version': '18.0.2.0.9',
    'website': 'https://www.sinetics.com.pe',
    'author': 'Sinetics',
    'summary': 'This module will generate the SIRE SUNAT format for the purchase and sales books.',
    'description': """
        This module will generate the SIRE SUNAT format for the purchase and sales books.
    """,
    'category': 'Accounting/Localizations',
    'module_type': 'official',
    'depends': [
        'ple_sale_book',
        'ple_purchase_book',
        'base'
    ],
    'data': [
        'security/ir.model.access.csv',
        'wizards/sire_purchase_complements_rate_wizard_views.xml',
        'wizards/sire_purchase_complements_wizard_views.xml',
        'wizards/sire_purchase_national_wizard_views.xml',
        'wizards/sire_purchase_not_domiciled_wizard_views.xml',
        'wizards/sire_sale_add_proposed_wizard_views.xml',
        'wizards/sire_sale_wizard_views.xml',
        'views/account_move_views.xml',
        'views/account_menuitem.xml',
        'views/res_company_views.xml',
        'sql/get_tax_purchase.sql',
        'sql/get_tax.sql',
        'sql/validate_string.sql'
    ],
    'installable': True,
    'auto_install': False,
    'license': 'Other proprietary',
    'currency': 'USD',
    'price': 200.00,
}
