from .report_inv_bal_base import InvBalReportBase


class InvBal314ReportExcel(InvBalReportBase):
    """Formato 3.14 - Beneficios sociales de los trabajadores (415).

    Columnas: documento de identidad (tipo Tabla 2, numero), apellidos y
    nombres del trabajador, saldo final.

    `data`: {'lines': [{doc_type, doc_number, name, balance}], 'total'}
    """

    FORMATO_CODE = '3.14'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 415 - Beneficios sociales '
                     'de los trabajadores por pagar')
    SHEET_NAME = 'F3.14 Beneficios Sociales'

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_BALANCE = 3

    def build(self, ws, workbook):
        f = self._formats
        widths = [14, 16, 60, 18]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        row = self._write_standard_header(ws, 0, self.COL_BALANCE)

        ws.set_row(row, 22)
        ws.set_row(row + 1, 22)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        ws.merge_range(row, self.COL_NAME, row + 1, self.COL_NAME,
                       'APELLIDOS Y NOMBRES DEL TRABAJADOR', f['col'])
        ws.merge_range(row, self.COL_BALANCE, row + 1, self.COL_BALANCE,
                       'SALDO FINAL', f['col'])
        ws.write(row + 1, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 1, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        row += 2

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_DOC_TYPE, str(line.get('doc_type') or ''), f['txt_center'])
            ws.write_string(row, self.COL_DOC_NUMBER, line.get('doc_number') or '', f['txt'])
            ws.write_string(row, self.COL_NAME, line.get('name') or '', f['txt_wrap'])
            ws.write_number(row, self.COL_BALANCE, float(line.get('balance') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_NAME,
                       'TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_BALANCE, float(self.data.get('total') or 0.0), f['total_num'])


class InvBal315ReportExcel(InvBalReportBase):
    """Formato 3.15 - Activo diferido (37) y pasivo diferido (49).

    Columnas: concepto, numero de comprobante de pago relacionado, saldo
    final.

    `data`: {'lines': [{concept, doc_ref, balance}], 'total'}
    """

    FORMATO_CODE = '3.15'
    FORMATO_TITLE = ('Detalle del saldo de la cuenta 37 - Activo diferido y de la '
                     'cuenta 49 - Pasivo diferido')
    SHEET_NAME = 'F3.15 Diferidos'

    COL_CONCEPT = 0
    COL_DOC_REF = 1
    COL_BALANCE = 2

    def build(self, ws, workbook):
        f = self._formats
        ws.set_column(self.COL_CONCEPT, self.COL_CONCEPT, 65)
        ws.set_column(self.COL_DOC_REF, self.COL_DOC_REF, 24)
        ws.set_column(self.COL_BALANCE, self.COL_BALANCE, 18)

        row = self._write_standard_header(ws, 0, self.COL_BALANCE)

        ws.set_row(row, 36)
        headers = ['CONCEPTO', 'NÚMERO DE COMPROBANTE DE PAGO RELACIONADO', 'SALDO FINAL']
        for col, header in enumerate(headers):
            ws.write(row, col, header, f['col'])
        row += 1

        for line in self.data.get('lines', []):
            ws.write_string(row, self.COL_CONCEPT, line.get('concept') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_DOC_REF, line.get('doc_ref') or '', f['txt_center'])
            ws.write_number(row, self.COL_BALANCE, float(line.get('balance') or 0.0), f['num'])
            row += 1

        ws.merge_range(row, self.COL_CONCEPT, row, self.COL_DOC_REF,
                       'TOTAL', f['total_lbl_right'])
        ws.write_number(row, self.COL_BALANCE, float(self.data.get('total') or 0.0), f['total_num'])


class InvBal316ReportExcel(InvBalReportBase):
    """Formato 3.16 - Capital (cuenta 50).

    Dos bloques: (1) detalle de la participacion accionaria (capital,
    valor nominal, acciones suscritas y pagadas, numero de accionistas) y
    (2) estructura de participacion (documento, nombre, tipo de acciones,
    numero de acciones, porcentaje).

    `data`: {'capital', 'nominal_value', 'subscribed_shares',
    'paid_shares', 'shareholders_count', 'shareholders': [{doc_type,
    doc_number, name, share_type, shares, percentage}]}
    Los valores None se imprimen en blanco.
    """

    FORMATO_CODE = '3.16'
    FORMATO_TITLE = 'Detalle del saldo de la cuenta 50 - Capital'
    SHEET_NAME = 'F3.16 Capital'

    COL_DOC_TYPE = 0
    COL_DOC_NUMBER = 1
    COL_NAME = 2
    COL_SHARE_TYPE = 3
    COL_SHARES = 4
    COL_PERCENT = 5

    def build(self, ws, workbook):
        f = self._formats
        f['int'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter', 'num_format': '#,##0',
        })
        f['pct'] = workbook.add_format({
            'size': 10, 'border': 1, 'valign': 'vcenter', 'num_format': '0.00%',
        })
        f['section_title'] = workbook.add_format({
            'bold': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
        })
        widths = [14, 16, 44, 16, 20, 18]
        for col, width in enumerate(widths):
            ws.set_column(col, col, width)

        row = self._write_standard_header(ws, 0, self.COL_PERCENT)

        # --- Bloque 1: detalle de la participacion accionaria -------------
        ws.write(row, 0, 'DETALLE DE LA PARTICIPACIÓN ACCIONARIA O PARTICIPACIONES SOCIALES',
                 f['section_title'])
        row += 1
        date_label = self.obj.date_end.strftime('%d.%m') if self.obj.date_end else ''
        items = [
            ('CAPITAL SOCIAL O PARTICIPACIONES SOCIALES AL %s' % date_label,
             self.data.get('capital'), 'num'),
            ('VALOR NOMINAL POR ACCIÓN O PARTICIPACIÓN SOCIAL',
             self.data.get('nominal_value'), 'num'),
            ('NÚMERO DE ACCIONES O PARTICIPACIONES SOCIALES SUSCRITAS',
             self.data.get('subscribed_shares'), 'int'),
            ('NÚMERO DE ACCIONES O PARTICIPACIONES SOCIALES PAGADAS',
             self.data.get('paid_shares'), 'int'),
            ('NÚMERO DE ACCIONISTAS O SOCIOS',
             self.data.get('shareholders_count'), 'int'),
        ]
        for label, value, fmt in items:
            ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_SHARE_TYPE, label, f['line_lbl'])
            ws.merge_range(row, self.COL_SHARES, row, self.COL_PERCENT, '', f[fmt])
            if value is not None:
                ws.write_number(row, self.COL_SHARES, float(value), f[fmt])
            row += 1
        row += 1

        # --- Bloque 2: estructura de participacion -----------------------
        ws.write(row, 0, 'ESTRUCTURA DE PARTICIPACIÓN ACCIONARIA O DE PARTICIPACIONES SOCIALES',
                 f['section_title'])
        row += 1
        ws.set_row(row, 22)
        ws.set_row(row + 1, 36)
        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_DOC_NUMBER,
                       'DOCUMENTO DE IDENTIDAD', f['col'])
        for col, label in ((self.COL_NAME, 'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL DEL ACCIONISTA O SOCIO'),
                           (self.COL_SHARE_TYPE, 'TIPO DE ACCIONES'),
                           (self.COL_SHARES, 'NÚMERO DE ACCIONES O DE PARTICIPACIONES SOCIALES'),
                           (self.COL_PERCENT, 'PORCENTAJE TOTAL DE PARTICIPACIÓN')):
            ws.merge_range(row, col, row + 1, col, label, f['col'])
        ws.write(row + 1, self.COL_DOC_TYPE, 'TIPO (TABLA 2)', f['col'])
        ws.write(row + 1, self.COL_DOC_NUMBER, 'NÚMERO', f['col'])
        row += 2

        shareholders = self.data.get('shareholders') or []
        for holder in shareholders:
            ws.write_string(row, self.COL_DOC_TYPE, str(holder.get('doc_type') or ''), f['txt_center'])
            ws.write_string(row, self.COL_DOC_NUMBER, holder.get('doc_number') or '', f['txt'])
            ws.write_string(row, self.COL_NAME, holder.get('name') or '', f['txt_wrap'])
            ws.write_string(row, self.COL_SHARE_TYPE, holder.get('share_type') or '', f['txt_center'])
            ws.write_number(row, self.COL_SHARES, float(holder.get('shares') or 0.0), f['int'])
            ws.write_number(row, self.COL_PERCENT, float(holder.get('percentage') or 0.0), f['pct'])
            row += 1
        if not shareholders:
            for col in range(self.COL_DOC_TYPE, self.COL_PERCENT + 1):
                ws.write_blank(row, col, None, f['txt'])
            row += 1

        ws.merge_range(row, self.COL_DOC_TYPE, row, self.COL_SHARE_TYPE,
                       'TOTALES', f['total_lbl_right'])
        if shareholders:
            ws.write_number(row, self.COL_SHARES,
                            float(sum(h.get('shares') or 0.0 for h in shareholders)), f['total_num'])
            ws.write_number(row, self.COL_PERCENT,
                            float(sum(h.get('percentage') or 0.0 for h in shareholders)), f['pct'])
        else:
            ws.write_blank(row, self.COL_SHARES, None, f['total_num'])
            ws.write_blank(row, self.COL_PERCENT, None, f['total_num'])