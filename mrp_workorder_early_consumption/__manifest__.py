{
    'name': 'MRP Workorder Early Consumption',
    'version': '18.0.1.2.1',
    'category': 'Manufacturing/Manufacturing',
    'summary': 'Consume BoM components assigned to a Work Order when the Work Order is completed (native stock moves).',
    'license': 'LGPL-3',
    'depends': [
        'mrp',
        'stock',
        'stock_account',
        'mrp_account',
        'mrp_workorder',
    ],
    'data': [
        # 'security/ir.model.access.csv',
        'views/mrp_workorder_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
