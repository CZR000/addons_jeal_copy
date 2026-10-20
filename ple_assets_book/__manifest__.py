{
    'name': 'Reporte PLE assets book',
    'version': '18.0.1.0.2',
    'website': 'https://www.sinetics.com.pe',
    'author': 'Sinetics',
    'description': """""",
    'depends': [
        'merch_and_model_asset',
        'ple_sale_book',
        'account_asset',
    ],
    'data': [
        'data/ir_sequence_data.xml',
        'views/account_views.xml',
        'views/account_assets.xml',
        'views/ple_report_assets_book_views.xml',
        'security/ir.model.access.csv'
    ],
    'installable': True,
    'auto_install': False,
    'license': 'Other proprietary',
    'module_type': 'official',
    'price': 299.00
}
