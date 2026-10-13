from io import BytesIO

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


MONTHS_ES = {
    1: 'ENERO', 2: 'FEBRERO', 3: 'MARZO', 4: 'ABRIL',
    5: 'MAYO', 6: 'JUNIO', 7: 'JULIO', 8: 'AGOSTO',
    9: 'SEPTIEMBRE', 10: 'OCTUBRE', 11: 'NOVIEMBRE', 12: 'DICIEMBRE',
}


class InvBalReportBase(object):
    """Base comun para los constructores de Excel de los formatos 3.x del
    Libro de Inventarios y Balances.

    Cada formato concreto hereda de esta clase y define:
      - FORMATO_CODE  (ej. '3.1')
      - FORMATO_TITLE (titulo oficial SUNAT del formato)
      - SHEET_NAME    (nombre de la hoja)
      - build(ws, workbook)  -> escribe el contenido del formato

    Reutiliza el patron del Libro Caja 1.1: registro de formatos de celda,
    cabecera estandar (Formato / Ejercicio / RUC / Razon Social) y el
    armado de get_content()/get_filename().
    """

    FORMATO_CODE = ''
    FORMATO_TITLE = ''
    SHEET_NAME = 'Reporte'
    LANDSCAPE = False

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data
        self._formats = {}

    # ------------------------------------------------------------------
    # API publica
    # ------------------------------------------------------------------
    def get_content(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        self.write_sheet(workbook)
        workbook.close()
        output.seek(0)
        return output.read()

    def write_sheet(self, workbook):
        """Agrega la hoja del formato a `workbook` (propio o consolidado)."""
        ws = workbook.add_worksheet(self.SHEET_NAME)
        if self.LANDSCAPE:
            ws.set_landscape()
        ws.set_paper(9)                     # A4
        ws.set_margins(0.2, 0.2, 0.3, 0.5)
        ws.fit_to_pages(1, 0)
        ws.set_footer(
            '&L&8Formato %s&R&8Página &P de &N' % self.FORMATO_CODE,
            {'margin': 0.2},
        )
        # Los formatos de celda pertenecen a cada workbook.
        self._formats = {}
        self._register_formats(workbook)
        self.build(ws, workbook)
        return ws

    def get_filename(self):
        company = self.obj.company_id
        period = self.obj.date_end.strftime('%Y%m') if self.obj.date_end else ''
        safe = ''.join(
            c if c.isalnum() else '_' for c in (company.name or 'company')
        )
        code = self.FORMATO_CODE.replace('.', '_')
        return 'Libro_Inv_Bal_%s_%s_%s.xlsx' % (code, safe, period)

    # ------------------------------------------------------------------
    # A implementar por cada formato
    # ------------------------------------------------------------------
    def build(self, ws, workbook):
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Formatos de celda compartidos
    # ------------------------------------------------------------------
    def _register_formats(self, workbook):
        f = self._formats
        f['title'] = workbook.add_format({
            'bold': True, 'size': 11, 'align': 'center', 'valign': 'vcenter',
            'text_wrap': True,
        })
        f['hdr_lbl'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        f['hdr_val'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        f['col'] = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'border': 1, 'size': 10, 'bg_color': '#D9E1F2', 'text_wrap': True,
        })
        f['section'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'bg_color': '#BFBFBF', 'border': 1,
        })
        f['line_lbl'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1,
        })
        f['total_lbl'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#F2F2F2',
        })
        f['total_lbl_right'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'right', 'valign': 'vcenter',
            'border': 1, 'bg_color': '#F2F2F2',
        })
        f['txt'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
        })
        f['txt_wrap'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter', 'text_wrap': True,
        })
        f['txt_center'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
        })
        f['date'] = workbook.add_format({
            'size': 10, 'border': 1, 'align': 'center', 'valign': 'vcenter',
            'num_format': 'dd/mm/yyyy',
        })
        f['num'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00;-#,##0.00;"-"',
        })
        f['total_num'] = workbook.add_format({
            'bold': True, 'size': 10, 'border': 1, 'valign': 'vcenter',
            'num_format': '#,##0.00;-#,##0.00;"-"', 'bg_color': '#F2F2F2',
        })
        f['blank'] = workbook.add_format({})

    # ------------------------------------------------------------------
    # Cabecera estandar SUNAT (Formato / Ejercicio / RUC / Razon Social)
    # ------------------------------------------------------------------
    def _write_standard_header(self, ws, row, span_last_col):
        """Escribe el bloque de cabecera comun. Retorna la fila siguiente."""
        company = self.obj.company_id
        f = self._formats

        title = 'FORMATO %s: "LIBRO DE INVENTARIOS Y BALANCES - %s"' % (
            self.FORMATO_CODE, (self.FORMATO_TITLE or '').upper(),
        )
        ws.set_row(row, 32)
        ws.merge_range(row, 0, row, span_last_col, title, f['title'])
        row += 2

        ws.write_rich_string(
            row, 0,
            f['hdr_lbl'], 'EJERCICIO:  ',
            f['hdr_val'], self.obj.date_end.strftime('%Y') if self.obj.date_end else '-',
        )
        row += 1
        ws.write_rich_string(
            row, 0,
            f['hdr_lbl'], 'RUC:  ',
            f['hdr_val'], company.vat or '-',
        )
        row += 1
        ws.write_rich_string(
            row, 0,
            f['hdr_lbl'], 'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL:  ',
            f['hdr_val'], company.name or '-',
        )
        row += 2
        return row

    # ------------------------------------------------------------------
    # Helpers de escritura
    # ------------------------------------------------------------------
    def _write_date(self, ws, row, col, value, fmt_key='date'):
        """Escribe una fecha (date/datetime) o texto si no es fecha."""
        f = self._formats
        if value and hasattr(value, 'year'):
            ws.write_datetime(row, col, value, f[fmt_key])
        else:
            ws.write(row, col, value or '', f['txt_center'])