from .report_inv_bal_base import InvBalReportBase


class InvBalPartnerReportBase(InvBalReportBase):
    """Base para los formatos de detalle por tercero (3.3, 3.4 y luego
    3.5, 3.12, 3.13...): tipo y numero de documento de identidad,
    nombre / razon social, monto y fecha.

    Cada formato define las etiquetas PARTY_LABEL, AMOUNT_LABEL y
    DATE_LABEL.

    `data` es el dict devuelto por _get_open_items():
        {'lines': [{doc_type, doc_number, name, amount, date}], 'total'}
    """

    PARTY_LABEL = 'INFORMACIÓN DEL CLIENTE'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR COBRAR'
    DATE_LABEL = 'FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO'

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_AMOUNT = 3
    COL_DATE = 4

    def build(self, ws, workbook):
        self._set_columns(ws)
        row = self._write_standard_header(ws, 0, self.COL_DATE)
        row = self._write_table_header(ws, row)
        for line in self.data.get('lines', []):
            row = self._write_line(ws, row, line)
        self._write_totals(ws, row)

    def _set_columns(self, ws):
        ws.set_column(self.COL_DOC_TYPE, self.COL_DOC_TYPE, 14)
        ws.set_column(self.COL_DOC_NUMBER, self.COL_DOC_NUMBER, 16)
        ws.set_column(self.COL_NAME, self.COL_NAME, 55)
        ws.set_column(self.COL_AMOUNT, self.COL_AMOUNT, 18)
        ws.set_column(self.COL_DATE, self.COL_DATE, 20)

    def _write_table_header(self, ws, row):
        f = self._formats
        ws.set_row(row, 20)
        ws.set_row(row + 1, 20)
        ws.set_row(row + 2, 30)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       self.PARTY_LABEL, f['col'])
        ws.merge_range(row, self.COL_AMOUNT, row + 2, self.COL_AMOUNT,
                       self.AMOUNT_LABEL, f['col'])
        ws.merge_range(row, self.COL_DATE, row + 2, self.COL_DATE,
                       self.DATE_LABEL, f['col'])
        ws.merge_range(row + 1, self.COL_DOC_TYPE, row + 1, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.merge_range(row + 1, self.COL_NAME, row + 2, self.COL_NAME,
                       'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL', f['col'])
        ws.write(row + 2, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 2, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        return row + 3

    def _write_line(self, ws, row, line):
        f = self._formats
        ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
        ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
        ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
        ws.write_number(row, self.COL_AMOUNT, float(line.get('amount') or 0.0), f['num'])
        self._write_date(ws, row, self.COL_DATE, line.get('date'))
        return row + 1

    def _write_totals(self, ws, row):
        f = self._formats
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       'SALDO FINAL TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_AMOUNT,
                        float(self.data.get('total') or 0.0), f['total_num'])
        ws.write_blank(row, self.COL_DATE, None, f['total_num'])
        return row + 1


class InvBal33ReportExcel(InvBalPartnerReportBase):
    """Formato 3.3 - Clientes (cuenta 12)."""

    FORMATO_CODE = '3.3'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 12 - Clientes'
    SHEET_NAME = 'F3.3 Clientes'
    PARTY_LABEL = 'INFORMACIÓN DEL CLIENTE'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR COBRAR'
    DATE_LABEL = 'FECHA DE EMISIÓN DEL COMPROBANTE DE PAGO'


class InvBal34ReportExcel(InvBalPartnerReportBase):
    """Formato 3.4 - Cuentas por cobrar al personal y accionistas (cuenta 14)."""

    FORMATO_CODE = '3.4'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 14 - Cuentas por cobrar al '
                     'personal, a los accionistas (socios), directores y gerentes')
    SHEET_NAME = 'F3.4 Personal y Accionistas'
    PARTY_LABEL = 'INFORMACIÓN DEL ACCIONISTA, SOCIO O PERSONAL'
    AMOUNT_LABEL = 'MONTO DE LA CUENTA POR COBRAR'
    DATE_LABEL = 'FECHA DE INICIO DE LA OPERACIÓN'