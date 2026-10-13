# -*- coding: utf-8 -*-
{
    'name': 'PLE Purchase Book - Autorelleno No Domiciliado',
    'version': '18.0.1.2.1',
    'summary': 'Autorellena Serie, Correlativo y Tipo de Documento en facturas '
               'de proveedor No Domiciliado.',
    'description': """
Extiende ple_purchase_book para que, al activarse el flag "No Domiciliado" en
una factura de proveedor, se autocompleten los campos:

* Serie de Comprobante (inv_serie)
* Correlativo de Comprobante (inv_correlative)
* Tipo de Documento (inv_type_document) -> (91) Comprobante de No Domiciliado

Los valores se derivan de la Referencia de factura (campo `ref`), partiendo
por el primer guion. Los campos siguen siendo editables manualmente.
    """,
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'category': 'Accounting/Localizations',
    'license': 'LGPL-3',
    'depends': [
        'ple_purchase_book',
        'l10n_pe',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
