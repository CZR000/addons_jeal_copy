{
    'name': 'Account Multicurrency Revaluation Dual Rate',
    'version': '18.0.1.4.0',
    'author': 'AlexJimmy159',
    'maintainer': 'AlexJimmy159',
    'support': 'AlexJimmy159@gmail.com',
    'website': 'https://github.com/AlexJimmy159',
    'summary': 'Multicurrency revaluation dual rate report',
    'description': """
This module allows you to generate a multicurrency revaluation report using dual rates.
""",
    'category': 'Accounting/Accounting',
    'depends': [
        # Odoo enterprise (repos_non_ent)
        'account_reports',
        'invoice_purchase_exchange_rate',
        'account_revaluation_closing_rate',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/multicurrency_revaluation_dual_rate_report.xml',
        'views/account_move_views.xml',
        'wizards/account_multicurrency_revaluation_dual_rate_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'account_multicurrency_revaluation_dual_rate/static/src/components/**/*',
        ],
    },
    'module_type': 'official',
    'application': False,
    'installable': True,
    'auto_install': False,
    'license': 'Other proprietary',
}
