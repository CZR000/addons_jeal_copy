from .report_inv_bal_base import InvBalReportBase


def _period_label(obj):
    if not obj.date_start or not obj.date_end:
        return ''
    return 'DEL %s AL %s' % (obj.date_start.strftime('%d/%m/%Y'),
                             obj.date_end.strftime('%d/%m/%Y'))


class _PeriodHeaderMixin(object):
    """Cabecera estandar + linea de periodo (los formatos 3.17 a 3.20 son
    de un periodo, no a una fecha)."""

    def _write_period_header(self, ws, span_last_col):
        f = self._formats
        row = self._write_standard_header(ws, 0, span_last_col)
        ws.write_rich_string(
            row - 1, 0,
            f['hdr_lbl'], 'PERÍODO:  ',
            f['hdr_val'], _period_label(self.obj),
        )
        return row


# ===========================================================================
# 3.17 - Balance de comprobacion
# ===========================================================================
class InvBal317ReportExcel(_PeriodHeaderMixin, InvBalReportBase):
    """Formato 3.17 - Balance de comprobacion (por subcuenta de 4 digitos).

    `data`: {'lines': [{code, name, init_debit, init_credit, mov_debit,
    mov_credit, final_debit, final_credit, bg_asset, bg_liability, pl_loss,
    pl_gain}], 'totals', 'result', 'grand_totals'}
    """

    FORMATO_CODE = '3.17'
    FORMATO_TITLE = 'Balance de comprobación'
    SHEET_NAME = 'F3.17 Balance Comprobacion'
    LANDSCAPE = True

    NUMERIC = ['init_debit', 'init_credit', 'mov_debit', 'mov_credit',
               'final_debit', 'final_credit', 'bg_asset', 'bg_liability',
               'pl_loss', 'pl_gain']

    def build(self, ws, workbook):
        f = self._formats
        ws.set_column(0, 0, 9)
        ws.set_column(1, 1, 38)
        ws.set_column(2, 11, 14)

        row = self._write_period_header(ws, 11)

        ws.set_row(row, 30)
        ws.set_row(row + 1, 30)
        groups = [
            (0, 1, 'CUENTA Y SUBCUENTA CONTABLE'),
            (2, 3, 'SALDOS INICIALES'),
            (4, 5, 'MOVIMIENTOS'),
            (6, 7, 'SALDOS FINALES'),
            (8, 9, 'SALDOS FINALES DEL BALANCE GENERAL'),
            (10, 11, 'SALDOS FINALES DEL ESTADO DE RESULTADOS POR NATURALEZA'),
        ]
        for first, last, label in groups:
            ws.merge_range(row, first, row, last, label, f['col'])
        subs = ['CÓDIGO', 'DENOMINACIÓN', 'DEUDOR', 'ACREEDOR', 'DEBE', 'HABER',
                'DEUDOR', 'ACREEDOR', 'ACTIVO', 'PASIVO Y PATRIMONIO',
                'PÉRDIDAS', 'GANANCIAS']
        for col, label in enumerate(subs):
            ws.write(row + 1, col, label, f['col'])
        row += 2

        for line in self.data.get('lines', []):
            ws.write_string(row, 0, line.get('code') or '', f['txt'])
            ws.write_string(row, 1, line.get('name') or '', f['txt_wrap'])
            for col, key in enumerate(self.NUMERIC, start=2):
                ws.write_number(row, col, float(line.get(key) or 0.0), f['num'])
            row += 1

        for label, values in (('TOTALES', self.data.get('totals') or {}),
                              ('RESULTADO DEL EJERCICIO O PERÍODO', self.data.get('result') or {}),
                              ('TOTALES', self.data.get('grand_totals') or {})):
            ws.merge_range(row, 0, row, 1, label, f['total_lbl_right'])
            for col, key in enumerate(self.NUMERIC, start=2):
                if key in values:
                    ws.write_number(row, col, float(values.get(key) or 0.0), f['total_num'])
                else:
                    ws.write_blank(row, col, None, f['total_num'])
            row += 1


# ===========================================================================
# Base para estados de "descripcion | importe" (3.18 y 3.20)
# ===========================================================================
class _StatementReportBase(_PeriodHeaderMixin, InvBalReportBase):
    """Estado financiero de dos columnas: descripcion e importe.

    Subclases definen ROWS: lista de (tipo, etiqueta, clave) donde tipo es
    'section' | 'label' | 'line' | 'total' | 'blank'. `data` es un dict
    {clave: importe}; una clave ausente o None se imprime en blanco.
    """

    ROWS = []

    def build(self, ws, workbook):
        f = self._formats
        f['indent'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1,
            'indent': 2, 'text_wrap': True,
        })
        f['label_only'] = workbook.add_format({
            'italic': True, 'size': 10, 'align': 'left', 'valign': 'vcenter',
            'border': 1, 'indent': 1,
        })
        ws.set_column(0, 0, 90)
        ws.set_column(1, 1, 20)

        row = self._write_period_header(ws, 1)
        ws.set_row(row, 22)
        ws.write(row, 0, 'DESCRIPCIÓN', f['col'])
        ws.write(row, 1, 'EJERCICIO O PERÍODO', f['col'])
        row += 1

        for kind, label, key in self.ROWS:
            if kind == 'blank':
                row += 1
                continue
            if kind == 'section':
                ws.merge_range(row, 0, row, 1, label, f['section'])
                row += 1
                continue
            if kind == 'label':
                ws.write(row, 0, label, f['label_only'])
                ws.write_blank(row, 1, None, f['num'])
                row += 1
                continue
            lbl_fmt = f['total_lbl'] if kind == 'total' else f['indent']
            num_fmt = f['total_num'] if kind == 'total' else f['num']
            ws.write(row, 0, label, lbl_fmt)
            value = self.data.get(key) if key else None
            if value is None:
                ws.write_blank(row, 1, None, num_fmt)
            else:
                ws.write_number(row, 1, float(value), num_fmt)
            row += 1


# ===========================================================================
# 3.18 - Estado de flujos de efectivo
# ===========================================================================
class InvBal318ReportExcel(_StatementReportBase):
    """Formato 3.18 - Estado de flujos de efectivo (metodo directo) con la
    conciliacion del resultado neto. Pagos en negativo."""

    FORMATO_CODE = '3.18'
    FORMATO_TITLE = 'Estado de flujos de efectivo'
    SHEET_NAME = 'F3.18 Flujos de Efectivo'

    ROWS = [
        ('section', 'ACTIVIDADES DE OPERACIÓN', None),
        ('line', 'Cobranza de venta de bienes o servicios e ingresos operacionales', 'op_cobro_ventas'),
        ('line', 'Cobranza de regalías, honorarios, comisiones y otros', 'op_cobro_regalias'),
        ('line', 'Cobranza de intereses y dividendos recibidos', 'op_cobro_intereses'),
        ('line', 'Otros cobros de efectivo relativos a la actividad', 'op_otros_cobros'),
        ('label', 'Menos:', None),
        ('line', 'Pago a proveedores de bienes y servicios', 'op_pago_proveedores'),
        ('line', 'Pago de remuneraciones y beneficios sociales', 'op_pago_remuneraciones'),
        ('line', 'Pago de tributos', 'op_pago_tributos'),
        ('line', 'Pago de intereses y rendimientos', 'op_pago_intereses'),
        ('line', 'Otros pagos de efectivo relativos a la actividad', 'op_otros_pagos'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo Provenientes de Actividades de Operación', 'op_total'),
        ('blank', '', None),
        ('section', 'ACTIVIDADES DE INVERSIÓN', None),
        ('line', 'Cobranza de venta de valores e inversiones permanentes', 'inv_cobro_valores'),
        ('line', 'Cobranza de venta de inmuebles, maquinaria y equipo', 'inv_cobro_ime'),
        ('line', 'Cobranza de venta de activos intangibles', 'inv_cobro_intang'),
        ('line', 'Otros cobros de efectivo relativos a la actividad', 'inv_otros_cobros'),
        ('label', 'Menos:', None),
        ('line', 'Pagos por compra de valores e inversiones permanentes', 'inv_pago_valores'),
        ('line', 'Pagos por compra de inmuebles, maquinaria y equipo', 'inv_pago_ime'),
        ('line', 'Pagos por compra de activos intangibles', 'inv_pago_intang'),
        ('line', 'Otros pagos de efectivo relativos a la actividad', 'inv_otros_pagos'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo Provenientes de Actividades de Inversión', 'inv_total'),
        ('blank', '', None),
        ('section', 'ACTIVIDADES DE FINANCIAMIENTO', None),
        ('line', 'Cobranza de emisión de acciones o nuevos aportes', 'fin_cobro_acciones'),
        ('line', 'Cobranza de recursos obtenidos por emisión de valores u otras obligaciones de largo plazo', 'fin_cobro_obligaciones'),
        ('line', 'Otros cobros de efectivo relativos a la actividad', 'fin_otros_cobros'),
        ('label', 'Menos:', None),
        ('line', 'Pagos de amortización o cancelación de valores u otras obligaciones de largo plazo', 'fin_pago_obligaciones'),
        ('line', 'Pago de dividendos y otras distribuciones', 'fin_pago_dividendos'),
        ('line', 'Otros pagos de efectivo relativos a la actividad', 'fin_otros_pagos'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo Provenientes de Actividades de Financiamiento', 'fin_total'),
        ('blank', '', None),
        ('total', 'Aumento (Disminución) Neto de Efectivo y Equivalente de Efectivo', 'net_change'),
        ('total', 'Saldo Efectivo y Equivalente de Efectivo al Inicio del Ejercicio', 'cash_initial'),
        ('total', 'Saldo Efectivo y Equivalente de Efectivo al Finalizar el Ejercicio', 'cash_final'),
        ('blank', '', None),
        ('section', 'CONCILIACIÓN DEL RESULTADO NETO CON EL EFECTIVO Y EQUIVALENTE DE EFECTIVO PROVENIENTE DE LAS ACTIVIDADES DE OPERACIÓN', None),
        ('total', 'Utilidad (Pérdida) neta del Ejercicio', 'net_result'),
        ('label', 'Más: Ajustes a la Utilidad (Pérdida) del Ejercicio', None),
        ('line', 'Depreciación y amortización del período', 'adj_depreciation'),
        ('line', 'Provisión Beneficios Sociales', 'adj_social_benefits'),
        ('line', 'Provisiones Diversas', 'adj_provisions'),
        ('line', 'Pérdida en venta de inmuebles, maquinaria y equipo', None),
        ('line', 'Pérdida en venta de valores e inversiones permanentes', None),
        ('line', 'Pérdida por activos monetarios no corrientes', None),
        ('line', 'Otros', 'adj_others'),
        ('label', 'Menos: Ajustes a la Utilidad (Pérdida) del Ejercicio', None),
        ('line', 'Utilidad en venta de inmuebles, maquinaria y equipo', None),
        ('line', 'Utilidad en venta de valores e inversiones permanentes', None),
        ('line', 'Ganancia por pasivos monetarios no corrientes', None),
        ('label', 'Cargos y Abonos por cambios netos en el Activo y Pasivo', None),
        ('line', '(Aumento) Disminución de Cuentas por Cobrar Comerciales', 'wc_cxc_com'),
        ('line', '(Aumento) Disminución de Cuentas por Cobrar Vinculadas', 'wc_cxc_vinc'),
        ('line', '(Aumento) Disminución de Otras Cuentas por Cobrar', 'wc_otras_cxc'),
        ('line', '(Aumento) Disminución en Existencias', 'wc_exist'),
        ('line', '(Aumento) Disminución en Gastos Pagados por Anticipado', 'wc_gpa'),
        ('line', 'Aumento (Disminución) de Cuentas por Pagar Comerciales', 'wc_cxp_com'),
        ('line', 'Aumento (Disminución) de Cuentas por Pagar Vinculadas', 'wc_cxp_vinc'),
        ('line', 'Aumento (Disminución) de Otras Cuentas por Pagar', 'wc_otras_cxp'),
        ('total', 'Aumento (Disminución) del Efectivo y Equivalente de Efectivo proveniente de las Actividades de Operación', 'op_total'),
    ]


# ===========================================================================
# 3.19 - Estado de cambios en el patrimonio neto
# ===========================================================================
class InvBal319ReportExcel(_PeriodHeaderMixin, InvBalReportBase):
    """Formato 3.19 - Estado de cambios en el patrimonio neto.

    `data`: {'columns': {clave: {'initial', 'final', 'rows': {'1'..'11':
    importe}}}, 'net_result'}
    """

    FORMATO_CODE = '3.19'
    FORMATO_TITLE = 'Estado de cambios en el patrimonio neto'
    SHEET_NAME = 'F3.19 Cambios Patrimonio'
    LANDSCAPE = True

    COLUMNS = [
        ('capital', 'CAPITAL'),
        ('capital_adic', 'CAPITAL ADICIONAL'),
        ('acciones_inv', 'ACCIONES DE INVERSIÓN'),
        ('exced_reval', 'EXCEDENTE DE REVALUACIÓN'),
        ('reserva_legal', 'RESERVA LEGAL'),
        ('otras_reservas', 'OTRAS RESERVAS'),
        ('res_acum', 'RESULTADOS ACUMULADOS'),
    ]
    ROWS = [
        ('1', '1. Efecto acumulado de los cambios en las políticas contables y la corrección de errores sustanciales'),
        ('2', '2. Distribuciones o asignaciones de utilidades efectuadas en el período'),
        ('3', '3. Dividendos y participaciones acordados durante el período'),
        ('4', '4. Nuevos aportes de accionistas'),
        ('5', '5. Movimiento de prima en la colocación de aportes y donaciones'),
        ('6', '6. Incrementos o disminuciones por fusiones o escisiones'),
        ('7', '7. Revaluación de activos'),
        ('8', '8. Capitalización de partidas patrimoniales'),
        ('9', '9. Redención de acciones de inversión o reducción de capital'),
        ('10', '10. Utilidad (pérdida) neta del ejercicio'),
        ('11', '11. Otros incrementos o disminuciones de las partidas patrimoniales'),
    ]

    def build(self, ws, workbook):
        f = self._formats
        f['concept'] = workbook.add_format({
            'size': 10, 'align': 'left', 'valign': 'vcenter', 'border': 1, 'text_wrap': True,
        })
        n_cols = len(self.COLUMNS)
        total_col = n_cols + 1
        ws.set_column(0, 0, 52)
        ws.set_column(1, total_col, 15)

        row = self._write_period_header(ws, total_col)
        ws.set_row(row, 36)
        ws.write(row, 0, 'CONCEPTOS', f['col'])
        for col, (_key, label) in enumerate(self.COLUMNS, start=1):
            ws.write(row, col, label, f['col'])
        ws.write(row, total_col, 'TOTAL', f['col'])
        row += 1

        columns = self.data.get('columns') or {}

        def write_row(label, getter, label_fmt, num_fmt):
            ws.write(row, 0, label, label_fmt)
            total = 0.0
            for col, (key, _label) in enumerate(self.COLUMNS, start=1):
                value = getter(columns.get(key) or {})
                total += value
                ws.write_number(row, col, value, num_fmt)
            ws.write_number(row, total_col, total, num_fmt)

        start = self.obj.date_start.strftime('%d/%m/%Y') if self.obj.date_start else ''
        end = self.obj.date_end.strftime('%d/%m/%Y') if self.obj.date_end else ''

        write_row('SALDOS AL %s' % start, lambda c: float(c.get('initial') or 0.0),
                  f['total_lbl'], f['total_num'])
        row += 1
        for row_key, label in self.ROWS:
            write_row(label, lambda c, k=row_key: float((c.get('rows') or {}).get(k) or 0.0),
                      f['concept'], f['num'])
            row += 1
        write_row('SALDOS AL %s' % end, lambda c: float(c.get('final') or 0.0),
                  f['total_lbl'], f['total_num'])


# ===========================================================================
# 3.20 - Estado de resultados por funcion
# ===========================================================================
class InvBal320ReportExcel(_StatementReportBase):
    """Formato 3.20 - Estado de ganancias y perdidas por funcion.
    Ingresos en positivo y gastos en negativo."""

    FORMATO_CODE = '3.20'
    FORMATO_TITLE = 'Estado de ganancias y pérdidas por función'
    SHEET_NAME = 'F3.20 Resultados'

    ROWS = [
        ('line', 'Ventas Netas (ingresos operacionales)', 'ventas'),
        ('line', 'Otros Ingresos Operacionales', 'otros_ing_op'),
        ('total', 'Total de Ingresos Brutos', 'total_ingresos'),
        ('blank', '', None),
        ('line', 'Costo de ventas', 'costo_ventas'),
        ('total', 'Utilidad Bruta', 'utilidad_bruta'),
        ('blank', '', None),
        ('section', 'GASTOS OPERACIONALES', None),
        ('line', 'Gastos de Administración', 'gastos_adm'),
        ('line', 'Gastos de Venta', 'gastos_venta'),
        ('total', 'Utilidad Operativa', 'utilidad_operativa'),
        ('blank', '', None),
        ('section', 'OTROS INGRESOS (GASTOS)', None),
        ('line', 'Ingresos Financieros', 'ingresos_fin'),
        ('line', 'Gastos Financieros', 'gastos_fin'),
        ('line', 'Otros Ingresos', 'otros_ingresos'),
        ('line', 'Otros Gastos', 'otros_gastos'),
        ('line', 'Resultados por Exposición a la Inflación', None),
        ('total', 'Resultados antes de Participaciones, Impuesto a la Renta y Partidas Extraordinarias', 'antes_part'),
        ('blank', '', None),
        ('line', 'Participaciones', 'participaciones'),
        ('line', 'Impuesto a la Renta', 'impuesto_renta'),
        ('total', 'Resultados antes de Partidas Extraordinarias', 'antes_extra'),
        ('blank', '', None),
        ('line', 'Ingresos Extraordinarios', None),
        ('line', 'Gastos Extraordinarios', None),
        ('total', 'Resultado Antes de Interés Minoritario', 'antes_minoritario'),
        ('line', 'Interés Minoritario', None),
        ('total', 'Utilidad (Pérdida) Neta del Ejercicio', 'utilidad_neta'),
        ('blank', '', None),
        ('line', 'Dividendos de Acciones Preferentes', None),
        ('total', 'Utilidad (pérdida) Neta atribuible a los Accionistas', 'utilidad_atribuible'),
        ('line', 'Utilidad (pérdida) Básica por Acción Común', None),
        ('line', 'Utilidad (pérdida) Básica por Acción de Inversión', None),
        ('line', 'Utilidad (pérdida) Diluida por Acción Común', None),
        ('line', 'Utilidad (pérdida) Diluida por Acción de Inversión', None),
    ]