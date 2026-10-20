{
    'name': 'PLE Libro de Inventarios y Balances',
    'version': '18.0.4.0.0',
    'category': 'Accounting/Localizations/Reporting',
    'summary': 'Reporte visual PLE Libro de Inventarios y Balances - Formatos 3.1 a 3.20',
    'description': """
Reporte PLE Libro de Inventarios y Balances - Formatos 3.1 a 3.20
=================================================================
Genera un Excel y un PDF con el layout visual de cada formato del
Libro de Inventarios y Balances (3.1 a 3.20) de SUNAT.

A diferencia de los libros de un solo formato, este libro expone en
una sola vista formulario una seccion por formato, cada una con su
propio boton "Generar Reporte 3.X" y sus descargas Excel / PDF, para
evitar generar un unico documento gigante.

El periodo se indica con Fecha Inicio y Fecha Fin. El Formato 3.1 toma
sus filas e importes del reporte contable Balance de situacion.
""",
    'author': 'Empiria',
    'website': 'https://empiria.com.pe',
    'license': 'LGPL-3',
    'depends': ['ple_diary_book', 'account_reports'],
    'data': [
        'security/ir.model.access.csv',
        'views/ple_report_inv_bal_views.xml',
        'views/account_account_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
