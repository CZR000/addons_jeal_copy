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


DEPRECIATION_METHOD_LABELS = {
    '1': 'LINEA RECTA',
    '2': 'UNIDADES PRODUCIDAS',
    '9': 'OTROS',
}


class AssetsReport(object):

    def __init__(self, obj, data):
        self.obj = obj
        self.data = data

    def _prepare_excel_rows(self):
        """The TXT keeps one row per accounting movement (asset-value line and
        depreciation line are separate, as SUNAT expects). The Excel the
        accountant reviews needs one row per asset instead, so this groups
        self.data by asset id and merges both kinds of lines into a single row
        matching the client's Formato 7.1 template."""
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

            account = asset.original_move_line_ids.account_id or asset.account_asset_id
            account_code = account[:1].code if account else ''

            saldo_inicial = asset.original_value or 0.00
            adquisiciones = total(lines, 'asset_amount')
            mejoras = total(lines, 'amount_improvement')
            retiros = total(lines, 'amount_withdrawals')
            otros_ajustes = total(lines, 'amount_other_adjustments')
            valor_historico = saldo_inicial + adquisiciones + mejoras + retiros + otros_ajustes
            ajuste_inflacion = total(lines, 'amount_inflation_adjustment')
            valor_ajustado = valor_historico + ajuste_inflacion

            dep_acum_cierre_anterior = total(lines, 'accumulated_depreciation_end_previous_year')
            dep_del_ejercicio = -total(lines, 'amount_depreciation_without_revaluation')
            dep_retiros = -total(lines, 'amount_depreciation_withdrawals')
            dep_otros_ajustes = -total(lines, 'amount_depreciation_other_adjustments')
            dep_acum_historica = dep_acum_cierre_anterior + dep_del_ejercicio + dep_retiros + dep_otros_ajustes
            ajuste_inflacion_dep = -total(lines, 'amount_depreciation_inflation')
            dep_acum_ajustada_inflacion = dep_acum_historica + ajuste_inflacion_dep

            rows.append({
                'codigo': asset.asset_code or '',
                'cuenta_contable': account_code,
                'descripcion': asset.name or '',
                'marca': asset.asset_brand or '-',
                'modelo': asset.asset_model or '-',
                'serie': asset.asset_series or '-',
                'saldo_inicial': saldo_inicial,
                'adquisiciones': adquisiciones,
                'mejoras': mejoras,
                'retiros': retiros,
                'otros_ajustes': otros_ajustes,
                'valor_historico': valor_historico,
                'ajuste_inflacion': ajuste_inflacion,
                'valor_ajustado': valor_ajustado,
                'fecha_adquisicion': first_non_empty(lines, 'acquisition_date'),
                'fecha_inicio_uso': first_non_empty(lines, 'start_date'),
                'metodo': DEPRECIATION_METHOD_LABELS.get(asset.depreciation_method, asset.depreciation_method or ''),
                'documento_autorizacion': asset.authorization_number_method_change or '',
                'porcentaje': asset.asset_rate or 0.00,
                'dep_acum_cierre_anterior': dep_acum_cierre_anterior,
                'dep_del_ejercicio': dep_del_ejercicio,
                'dep_retiros': dep_retiros,
                'dep_otros_ajustes': dep_otros_ajustes,
                'dep_acum_historica': dep_acum_historica,
                'ajuste_inflacion_dep': ajuste_inflacion_dep,
                'dep_acum_ajustada_inflacion': dep_acum_ajustada_inflacion,
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

        last_col = 25  # 26 columnas: 0..25

        ws = workbook.add_worksheet('REGISTRO DE ACTIVOS FIJOS')
        ws.set_column('A:A', 12)
        ws.set_column('B:B', 14)
        ws.set_column('C:C', 30)
        ws.set_column('D:F', 16)
        ws.set_column('G:N', 16)
        ws.set_column('O:P', 14)
        ws.set_column('Q:S', 14)
        ws.set_column('T:Z', 16)

        ws.merge_range(0, 0, 0, last_col, 'FORMATO 7.1: "REGISTRO DE ACTIVOS FIJOS - DETALLE DE LOS ACTIVOS FIJOS"', style_title)
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

        # Solo hay grupo fusionado donde la plantilla lo tiene: Detalle del
        # Activo Fijo y Depreciación (método/documento/porcentaje). El resto
        # de columnas van solas, igual que en la plantilla del cliente.
        groups = [
            (2, 5, 'DETALLE DEL ACTIVO FIJO'),
            (16, 18, 'DEPRECIACIÓN'),
        ]
        for col_start, col_end, label in groups:
            ws.merge_range(header_row, col_start, header_row, col_end, label, style_group)

        column_titles = [
            'Código relacionado con el Activo Fijo',
            'Cuenta contable del Activo Fijo',
            'Descripción',
            'Marca del Activo Fijo',
            'Modelo del Activo Fijo',
            'Número de serie y/o placa del Activo Fijo',
            'Saldo Inicial',
            'Adquisiciones/Adiciones',
            'Mejoras',
            'Retiros y/o Bajas',
            'Otros Ajustes',
            'Valor Histórico del Activo Fijo al 31.12',
            'Ajuste por Inflación',
            'Valor Ajustado del Activo Fijo al 31.12',
            'Fecha de Adquisición',
            'Fecha de Inicio del Uso',
            'Método Aplicado',
            'N° de Documento de Autorización',
            'Porcentaje de Depreciación',
            'Depreciación Acumulada al Cierre del Ejercicio Anterior',
            'Depreciación del Ejercicio',
            'Depreciación Relacionada con los Retiros y/o Bajas',
            'Depreciación Relacionada con Otros Ajustes',
            'Depreciación Acumulada Histórica',
            'Ajuste por Inflación de la Depreciación',
            'Depreciación Acumulada Ajustada por Inflación',
        ]
        for col, title in enumerate(column_titles):
            ws.write(column_row, col, title, style_column)

        # Columnas monetarias que sí se suman en la fila de TOTALES
        total_columns = list(range(6, 14)) + list(range(19, 26))

        rows = self._prepare_excel_rows()
        i = data_start_row
        for row in rows:
            ws.write(i, 0, row['codigo'], style_content)
            ws.write(i, 1, row['cuenta_contable'], style_content)
            ws.write(i, 2, row['descripcion'], style_content)
            ws.write(i, 3, row['marca'], style_content)
            ws.write(i, 4, row['modelo'], style_content)
            ws.write(i, 5, row['serie'], style_content)
            ws.write(i, 6, row['saldo_inicial'], style_number)
            ws.write(i, 7, row['adquisiciones'], style_number)
            ws.write(i, 8, row['mejoras'], style_number)
            ws.write(i, 9, row['retiros'], style_number)
            ws.write(i, 10, row['otros_ajustes'], style_number)
            ws.write(i, 11, row['valor_historico'], style_number)
            ws.write(i, 12, row['ajuste_inflacion'], style_number)
            ws.write(i, 13, row['valor_ajustado'], style_number)
            ws.write(i, 14, row['fecha_adquisicion'], style_content)
            ws.write(i, 15, row['fecha_inicio_uso'], style_content)
            ws.write(i, 16, row['metodo'], style_content)
            ws.write(i, 17, row['documento_autorizacion'], style_content)
            ws.write(i, 18, row['porcentaje'], style_number)
            ws.write(i, 19, row['dep_acum_cierre_anterior'], style_number)
            ws.write(i, 20, row['dep_del_ejercicio'], style_number)
            ws.write(i, 21, row['dep_retiros'], style_number)
            ws.write(i, 22, row['dep_otros_ajustes'], style_number)
            ws.write(i, 23, row['dep_acum_historica'], style_number)
            ws.write(i, 24, row['ajuste_inflacion_dep'], style_number)
            ws.write(i, 25, row['dep_acum_ajustada_inflacion'], style_number)

            i += 1

        total_row = i
        ws.merge_range(total_row, 0, total_row, 5, 'TOTALES', style_total_label)
        if i > data_start_row:
            first_data_row = data_start_row + 1
            last_data_row = i
            for col in range(6, 26):
                if col in total_columns:
                    col_letter = _xl_col_to_name(col)
                    formula = '=SUM({0}{1}:{0}{2})'.format(col_letter, first_data_row, last_data_row)
                    ws.write_formula(total_row, col, formula, style_total_number)
                else:
                    ws.write_blank(total_row, col, None, style_total_blocked)
        else:
            for col in range(6, 26):
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

        def format_txt_decimal(values, percent=False):
            if not percent:
                value_format = "{0:.2f}".format(round(values, 2))
            else:
                value_format = "{0:.2f}".format(values)
            return value_format

        raw = ''
        template = '{period}|{cuo}|{correlative}|{asset_catalog_code}|{asset_code}|{used_catalog_code}|' \
                   '{unique_fixed_asset_type}|{fixed_asset_type}|{account_code}|{fixed_asset_state}|{description}|' \
                   '{asset_brand}|{asset_model}|{asset_series}|{asset_opening}|{asset_amount}|' \
                   '{amount_improvement}|{amount_withdrawals}|{amount_other_adjustments}|{amount_voluntary_revaluation}|{amount_revaluation_reorganization}|' \
                   '{amount_other_revaluation}|{amount_inflation_adjustment}|{acquisition_date}|{start_date}|{code_calculation_depreciation}|' \
                   '{authorization_document_number}|{depreciation_percentage}|{accumulated_depreciation_end_previous_year}|{amount_depreciation_without_revaluation}|{amount_depreciation_withdrawals}|' \
                   '{amount_depreciation_other_adjustments}|{amount_depreciation_voluntary_revaluation}|{amount_depreciation_revaluation_reorganization}|{amount_depreciation_revaluations}|{amount_depreciation_inflation}|' \
                   '{state}|\r\n'

        for value in self.data:
            raw += template.format(
                period=value['period'],
                cuo=value['cuo'],
                correlative=value['correlative'],
                asset_catalog_code=value['asset_catalog_code'],
                asset_code=value['asset_code'],

                used_catalog_code=value['used_catalog_code'],

                unique_fixed_asset_type=value['unique_fixed_asset_type'],
                fixed_asset_type=value['fixed_asset_type'],
                account_code=value['account_code'],
                fixed_asset_state=value['fixed_asset_state'],
                description=value['description'],

                asset_brand=value['asset_brand'],
                asset_model=value['asset_model'],
                asset_series=value['asset_series'],
                asset_opening=value['asset_opening'],
                asset_amount="{:.2f}".format(value['asset_amount']),

                amount_improvement="{:.2f}".format(value['amount_improvement']),
                amount_withdrawals="{:.2f}".format(value['amount_withdrawals']),
                amount_other_adjustments="{:.2f}".format(value['amount_other_adjustments']),
                amount_voluntary_revaluation="{:.2f}".format(value['amount_voluntary_revaluation']),
                amount_revaluation_reorganization="{:.2f}".format(value['amount_revaluation_reorganization']),

                amount_other_revaluation="{:.2f}".format(value['amount_other_revaluation']),
                amount_inflation_adjustment=value['amount_inflation_adjustment'],
                acquisition_date=value['acquisition_date'],
                start_date=value['start_date'],
                code_calculation_depreciation=value['code_calculation_depreciation'],

                authorization_document_number=value['authorization_document_number'],
                depreciation_percentage="{:.2f}".format(value['depreciation_percentage']),
                accumulated_depreciation_end_previous_year="{:.2f}".format(value['accumulated_depreciation_end_previous_year']),
                amount_depreciation_without_revaluation="{:.2f}".format(value['amount_depreciation_without_revaluation']),
                amount_depreciation_withdrawals="{:.2f}".format(value['amount_depreciation_withdrawals']),

                amount_depreciation_other_adjustments="{:.2f}".format(value['amount_depreciation_other_adjustments']),
                amount_depreciation_voluntary_revaluation="{:.2f}".format(value['amount_depreciation_voluntary_revaluation']),
                amount_depreciation_revaluation_reorganization="{:.2f}".format(value['amount_depreciation_revaluation_reorganization']),
                amount_depreciation_revaluations="{:.2f}".format(value['amount_depreciation_revaluations']),
                amount_depreciation_inflation="{:.2f}".format(value['amount_depreciation_inflation']),

                state=1
            )
        return raw
