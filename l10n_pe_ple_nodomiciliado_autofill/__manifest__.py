# -*- coding: utf-8 -*-
{
    'name': 'PLE Purchase Book - Autorelleno No Domiciliado',
    'version': '18.0.2.0.0',
    'summary': 'Tipo de documento (91) en facturas No Domiciliado y control '
               'del sustento de crédito fiscal según SUNAT.',
    'description': """
Ajustes para facturas de proveedor marcadas como "No Domiciliado":

* Tipo de Documento de la cabecera (l10n_latam_document_type_id): se asigna
  (91) Comprobante de No Domiciliado (campo 4 del RCE No Domiciliados). Para
  el resto de facturas se respeta el cálculo estándar de Odoo.
* Sustento del crédito fiscal (pestaña No Domiciliado: inv_type_document,
  inv_serie, inv_correlative): ya NO se autorrellena desde la referencia.
  Lo completa el usuario. El tipo de documento solo admite los códigos
  aceptados por SUNAT para el campo 10: 00, 46, 50, 51, 52 y 53.

Cambios 18.0.2.0.0
------------------
* Se elimina el autorrelleno de Serie, Correlativo y Tipo de documento del
  sustento (provocaba los errores 418 y 403 de SUNAT).
* El cálculo del tipo de documento de cabecera llama al cálculo estándar
  antes de asignar el 91, para no afectar facturas nacionales.
* No se modifican datos existentes: las facturas que ya tienen el 91 en el
  sustento deben corregirse manualmente.
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
