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


class AssetsReport0703(object):

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data

    def _prepare_excel_rows(self):
        """self.data has one row per accounting movement (the 'active' pass and
        the 'depreciation' pass produce separate entries for the same asset,
        same as Formato 7.1). Group them by asset id into a single row matching
        the client's Formato 7.3 template."""
        groups = {}
        order = []
        for value in self.data:
            asset_id = value.get('id')
            if asset_id not in groups:
                groups[asset_id] = []
                order.append(asset_id)
            groups[asset_id].append(value)

        def total(lines, key):
            return sum(float(line.get(key) or 0) for line in lines)

        def first_non_empty(lines, key):
            for line in lines:
                if line.get(key):
                    return line[key]
            return ''

        AccountAsset = self.obj.env['account.asset']
        rows = []
        for asset_id in order:
            lines = groups[asset_id]
            asset = AccountAsset.browse(asset_id)

            valor_adq_extranjera = total(lines, 'value_acquisition_exchange')
            tipo_cambio_adquisicion = total(lines, 'foreign_currency_exchange_rate')
            valor_adq_nacional = total(lines, 'value_acquisition_local')
            tipo_cambio_3112 = total(lines, 'currency_exchange_rate_3112')
            ajuste_diferencia_cambio = total(lines, 'adjust_difference_exchange_rate')
            valor_moneda_nacional_3112 = valor_adq_nacional + ajuste_diferencia_cambio

            dep_del_ejercicio = total(lines, 'amount_withdrawals')
            dep_retiros = total(lines, 'dep_amount_withdrawals')
            dep_otros_ajustes = total(lines, 'amount_other_ple')
            dep_acum_historica = dep_del_ejercicio + dep_retiros + dep_otros_ajustes

            rows.append({
                'codigo': asset.asset_code or '',
                'fecha_adquisicion': first_non_empty(lines, 'acquisition_date'),
                'valor_adq_extranjera': valor_adq_extranjera,
                'tipo_cambio_adquisicion': tipo_cambio_adquisicion,
                'valor_adq_nacional': valor_adq_nacional,
                'tipo_cambio_3112': tipo_cambio_3112,
                'ajuste_diferencia_cambio': ajuste_diferencia_cambio,
                'valor_moneda_nacional_3112': valor_moneda_nacional_3112,
                'dep_del_ejercicio': dep_del_ejercicio,
                'dep_retiros': dep_retiros,
                'dep_otros_ajustes': dep_otros_ajustes,
                'dep_acum_historica': dep_acum_historica,
            })
        return rows

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

        last_col = 11  # 12 columnas: 0..11

        ws = workbook.add_worksheet('REGISTRO DE ACTIVOS FIJOS - DIFERENCIA DE CAMBIO')
        ws.set_column('A:A', 14)
        ws.set_column('B:L', 18)

        ws.merge_range(0, 0, 0, last_col, 'FORMATO 7.3: "REGISTRO DE ACTIVOS FIJOS - DETALLE DE LA DIFERENCIA DE CAMBIO"', style_title)
        ws.write(2, 0, 'PERÍODO:', style_label)
        ws.write(2, 1, '{} - {}'.format(self.obj.date_start.strftime('%d/%m/%Y'), self.obj.date_end.strftime('%d/%m/%Y')))
        ws.write(3, 0, 'RUC:', style_label)
        ws.write(3, 1, self.obj.company_id.vat or '')
        ws.write(4, 0, 'APELLIDOS Y NOMBRES, DENOMINACIÓN O RAZÓN SOCIAL:', style_label)
        ws.write(4, 1, self.obj.company_id.name or '')

        header_row = 6
        column_row = 7
        data_start_row = 8

        ws.set_row(header_row, 20)
        ws.set_row(column_row, 60)

        groups = [
            (1, 7, 'ACTIVO FIJO'),
            (8, 11, 'DEPRECIACIÓN'),
        ]
        for col_start, col_end, label in groups:
            ws.merge_range(header_row, col_start, header_row, col_end, label, style_group)

        column_titles = [
            'Código relacionado con el Activo Fijo',
            'Fecha de Adquisición',
            'Valor de Adquisición en Moneda Extranjera',
            'Tipo de Cambio en la Fecha de Adquisición',
            'Valor de Adquisición en Moneda Nacional',
            'Tipo de Cambio al 31.12',
            'Ajuste por Diferencia de Cambio',
            'Valor en Moneda Nacional al 31.12',
            'Del Ejercicio',
            'De los Retiros y/o Bajas',
            'De Otros Ajustes',
            'Acumulada Histórica',
        ]
        for col, title in enumerate(column_titles):
            ws.write(column_row, col, title, style_column)

        # Columnas monetarias que sí se suman en la fila de TOTALES
        total_columns = list(range(2, 12))

        rows = self._prepare_excel_rows()
        i = data_start_row
        for row in rows:
            ws.write(i, 0, row['codigo'], style_content)
            ws.write(i, 1, row['fecha_adquisicion'], style_content)
            ws.write(i, 2, row['valor_adq_extranjera'], style_number)
            ws.write(i, 3, row['tipo_cambio_adquisicion'], style_number)
            ws.write(i, 4, row['valor_adq_nacional'], style_number)
            ws.write(i, 5, row['tipo_cambio_3112'], style_number)
            ws.write(i, 6, row['ajuste_diferencia_cambio'], style_number)
            ws.write(i, 7, row['valor_moneda_nacional_3112'], style_number)
            ws.write(i, 8, row['dep_del_ejercicio'], style_number)
            ws.write(i, 9, row['dep_retiros'], style_number)
            ws.write(i, 10, row['dep_otros_ajustes'], style_number)
            ws.write(i, 11, row['dep_acum_historica'], style_number)

            i += 1

        total_row = i
        ws.merge_range(total_row, 0, total_row, 1, 'TOTALES', style_total_label)
        if i > data_start_row:
            first_data_row = data_start_row + 1
            last_data_row = i
            for col in range(2, 12):
                if col in total_columns:
                    col_letter = _xl_col_to_name(col)
                    formula = '=SUM({0}{1}:{0}{2})'.format(col_letter, first_data_row, last_data_row)
                    ws.write_formula(total_row, col, formula, style_total_number)
                else:
                    ws.write_blank(total_row, col, None, style_total_blocked)
        else:
            for col in range(2, 12):
                ws.write_blank(total_row, col, None, style_total_blocked)

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
        template = '{period}|{cuo}|{ple_correlative}|{asset_catalog_code}|{asset_code}|{acquisition_date}|' \
                   '{value_acquisition_exchange}|{foreign_currency_exchange_rate}|{value_acquisition_local}|'\
                   '{currency_exchange_rate_3112}|{adjust_difference_exchange_rate}|{amount_withdrawals}|'\
                   '{dep_amount_withdrawals}|{amount_other_ple}|1|\r\n'

        period = self.obj.date_start.strftime('%Y0000')
        for value in self.data:
            raw += template.format(
                period=period,
                cuo=value['cuo'],
                ple_correlative=value['correlative'],
                asset_catalog_code=value['asset_catalog_code'],
                asset_code=value['asset_code'],
                acquisition_date=value['acquisition_date'],
                value_acquisition_exchange=value['value_acquisition_exchange'],
                foreign_currency_exchange_rate=value['foreign_currency_exchange_rate'],
                value_acquisition_local=value['value_acquisition_local'],
                currency_exchange_rate_3112=value['currency_exchange_rate_3112'],
                adjust_difference_exchange_rate=value['adjust_difference_exchange_rate'],
                amount_withdrawals=value['amount_withdrawals'],
                dep_amount_withdrawals=value['dep_amount_withdrawals'],
                amount_other_ple=value['amount_other_ple'],

            )
        return raw
