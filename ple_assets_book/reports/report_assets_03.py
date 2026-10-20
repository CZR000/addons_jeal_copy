from io import BytesIO

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter


def _xl_col_to_name(col):
    """0-indexed column number to Excel column letter (0 -> 'A', 26 -> 'AA')."""
    name = ''
    col += 1
    while col:
        col, remainder = divmod(col - 1, 26)
        name = chr(65 + remainder) + name
    return name


class AssetsReport03(object):

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data

    def get_content_excel(self):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})

        style_title = workbook.add_format({
            'bold': True,
            'font_size': 12,
            'valign': 'vcenter',
        })
        style_label = workbook.add_format({
            'bold': True,
            'valign': 'vcenter',
            'size': 10,
        })
        style_group = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'size': 10,
            'bold': True,
            'bg_color': '#D9D9D9',
            'border': 7,
        })
        style_column = workbook.add_format({
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'size': 10,
            'bold': True,
            'border': 7
        })
        style_content = workbook.add_format({
            'valign': 'vcenter',
            'size': 10,
            'border': 7
        })
        style_number = workbook.add_format({
            'size': 10,
            'num_format': '#,##0.00',
            'border': 7
        })
        style_date = workbook.add_format({
            'size': 10,
            'num_format': 'dd/mm/yy',
            'border': 7
        })
        style_total_label = workbook.add_format({
            'bold': True,
            'valign': 'vcenter',
            'size': 10,
            'border': 7,
        })
        style_total_number = workbook.add_format({
            'bold': True,
            'size': 10,
            'num_format': '#,##0.00',
            'border': 7,
        })
        style_total_blocked = workbook.add_format({
            'bg_color': '#BFBFBF',
            'border': 7,
        })

        last_col = 4  # 5 columnas: 0..4

        ws = workbook.add_worksheet('REGISTRO DE ACTIVOS FIJOS - ARRENDAMIENTO FINANCIERO')
        ws.set_column('A:E', 22)

        ws.merge_range(0, 0, 0, last_col, 'FORMATO 7.4: "REGISTRO DE ACTIVOS FIJOS - DETALLE DE LOS ACTIVOS FIJOS BAJO LA MODALIDAD DE ARRENDAMIENTO FINANCIERO AL 31.12"', style_title)
        ws.write(2, 0, 'PERÍODO:', style_label)
        ws.write(2, 1, '{} - {}'.format(self.obj.date_start.strftime('%d/%m/%Y'), self.obj.date_end.strftime('%d/%m/%Y')))
        ws.write(3, 0, 'RUC:', style_label)
        ws.write(3, 1, self.obj.company_id.vat or '')
        ws.write(4, 0, 'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL:', style_label)
        ws.write(4, 1, self.obj.company_id.name or '')

        column_row = 7
        data_start_row = 8

        ws.set_row(column_row, 60)

        column_titles = [
            'Fecha del Contrato',
            'Número del Contrato de Arrendamiento Financiero',
            'Fecha de Inicio del Arrendamiento Financiero',
            'Número de Cuotas Pactadas',
            'Monto Total del Contrato de Arrendamiento Financiero',
        ]
        for col, title in enumerate(column_titles):
            ws.write(column_row, col, title, style_column)

        i = data_start_row
        for value in self.data:
            original_value = self.get_original_value(value['original_value'], value['value_acquisition_local'], value['id'], value['exchange_rate'])
            ws.write(i, 0, value['acquisition_date'], style_date)
            ws.write(i, 1, value['contract_number'], style_content)
            ws.write(i, 2, value['asset_date_init'], style_date)
            ws.write(i, 3, value['method_number'], style_content)
            ws.write(i, 4, original_value, style_number)

            i += 1

        total_row = i
        ws.merge_range(total_row, 0, total_row, 3, 'TOTAL', style_total_label)
        if i > data_start_row:
            first_data_row = data_start_row + 1
            last_data_row = i
            col_letter = _xl_col_to_name(4)
            formula = '=SUM({0}{1}:{0}{2})'.format(col_letter, first_data_row, last_data_row)
            ws.write_formula(total_row, 4, formula, style_total_number)
        else:
            ws.write_blank(total_row, 4, None, style_total_blocked)

        workbook.close()
        output.seek(0)
        return output.read()

    def get_filename(self, file_type, book_identifier):
        year = self.obj.date_start.strftime('%Y')
        return 'LE{vat}{period_year}{period_month}{period_day}{book_identifier}00{state_send}{has_info}11.{file_type}'.format(
            vat=self.obj.company_id.vat,
            period_year=year,
            period_month='00',
            period_day='00',
            book_identifier=book_identifier,
            state_send=self.obj.state_send or '',
            has_info=int(bool(self.data)),
            file_type=file_type
        )

    def get_content_txt(self):
        raw = ''
        template = '{period}|{cuo}|{ple_correlative}|{asset_catalog_code}|{contract_number}|{acquisition_date}|' \
                   '{asset_code}|{asset_date_init}|{method_number}|{original_value}|1|\r\n'

        period = self.obj.date_start.strftime('%Y0000')
        for value in self.data:
            original_value = self.get_original_value(value['original_value'], value['value_acquisition_local'], value['id'], value['exchange_rate'])
            raw += template.format(
                period=period,
                cuo=value['cuo'],
                ple_correlative=value['ple_correlative'],
                asset_catalog_code=value['asset_catalog_code'],
                contract_number=value['contract_number'],
                acquisition_date=value['acquisition_date'],
                asset_code=value['asset_code'],
                asset_date_init=value['asset_date_init'],
                method_number=value['method_number'],
                original_value="{0:.2f}".format(original_value),
            )
        return raw
    
    def get_original_value(self, original_value, value_acquisition_local, asset_id, exchange_rate):
        asset_id = self.obj.env['account.asset'].browse(asset_id)
        if value_acquisition_local:
            original_value = value_acquisition_local
        elif asset_id.currency_id.name != 'PEN':
            inverse_rate = False
            rate_inverse_company_rate = 0.00
            rate_inverse_company_rate_max = 0.00
            for rate_id in asset_id.currency_id.rate_ids:
                if rate_id.name == asset_id.acquisition_date:
                    rate_inverse_company_rate = rate_id.inverse_company_rate
                if rate_id[0].name:
                    rate_inverse_company_rate_max = rate_id.inverse_company_rate
            if exchange_rate:
                inverse_rate = exchange_rate
            if rate_inverse_company_rate:
                inverse_rate = rate_inverse_company_rate
            else:
                inverse_rate = rate_inverse_company_rate_max
            if inverse_rate:
                original_value = original_value * inverse_rate
        return original_value