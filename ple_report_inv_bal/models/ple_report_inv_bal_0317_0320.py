import logging
from datetime import timedelta

from odoo import models

from ..reports.report_inv_bal_0317_0320 import (
    InvBal317ReportExcel,
    InvBal318ReportExcel,
    InvBal319ReportExcel,
    InvBal320ReportExcel,
)

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 3.18 - Estado de Flujos de Efectivo (metodo directo)
# Cada linea de contrapartida de un asiento con efectivo (cuenta 10) aporta
# un flujo igual a -saldo. El flujo se clasifica por el prefijo de la cuenta
# de contrapartida (gana el prefijo mas largo): positivo -> cobro, negativo
# -> pago. Cuentas no listadas: otros cobros / otros pagos de operacion.
# CONFIRMAR / AJUSTAR con contabilidad.
# ---------------------------------------------------------------------------
EFE_MAP = {
    # --- Operacion ---
    '12': ('op_cobro_ventas', 'op_otros_pagos'),
    '13': ('op_cobro_ventas', 'op_otros_pagos'),
    '70': ('op_cobro_ventas', 'op_otros_pagos'),
    '74': ('op_cobro_ventas', 'op_otros_pagos'),
    '73': ('op_cobro_regalias', 'op_otros_pagos'),
    '75': ('op_cobro_regalias', 'op_otros_pagos'),
    '77': ('op_cobro_intereses', 'op_otros_pagos'),
    '776': ('op_otros_cobros', 'op_otros_pagos'),       # diferencia de cambio
    '676': ('op_otros_cobros', 'op_otros_pagos'),       # diferencia de cambio
    '20': ('op_otros_cobros', 'op_pago_proveedores'),
    '21': ('op_otros_cobros', 'op_pago_proveedores'),
    '24': ('op_otros_cobros', 'op_pago_proveedores'),
    '25': ('op_otros_cobros', 'op_pago_proveedores'),
    '26': ('op_otros_cobros', 'op_pago_proveedores'),
    '28': ('op_otros_cobros', 'op_pago_proveedores'),
    '42': ('op_otros_cobros', 'op_pago_proveedores'),
    '43': ('op_otros_cobros', 'op_pago_proveedores'),
    '60': ('op_otros_cobros', 'op_pago_proveedores'),
    '63': ('op_otros_cobros', 'op_pago_proveedores'),
    '41': ('op_otros_cobros', 'op_pago_remuneraciones'),
    '62': ('op_otros_cobros', 'op_pago_remuneraciones'),
    '40': ('op_otros_cobros', 'op_pago_tributos'),
    '64': ('op_otros_cobros', 'op_pago_tributos'),
    '67': ('op_otros_cobros', 'op_pago_intereses'),
    # --- Inversion ---
    '11': ('inv_cobro_valores', 'inv_pago_valores'),
    '30': ('inv_cobro_valores', 'inv_pago_valores'),
    '31': ('inv_cobro_valores', 'inv_pago_valores'),
    '32': ('inv_cobro_ime', 'inv_pago_ime'),
    '33': ('inv_cobro_ime', 'inv_pago_ime'),
    '34': ('inv_cobro_intang', 'inv_pago_intang'),
    '35': ('inv_otros_cobros', 'inv_otros_pagos'),
    '38': ('inv_otros_cobros', 'inv_otros_pagos'),
    # --- Financiamiento ---
    '45': ('fin_cobro_obligaciones', 'fin_pago_obligaciones'),
    '50': ('fin_cobro_acciones', 'fin_otros_pagos'),
    '51': ('fin_cobro_acciones', 'fin_otros_pagos'),
    '52': ('fin_cobro_acciones', 'fin_otros_pagos'),
    '44': ('fin_otros_cobros', 'fin_pago_dividendos'),
    '59': ('fin_otros_cobros', 'fin_pago_dividendos'),
    '49': ('fin_otros_cobros', 'fin_otros_pagos'),
    '56': ('fin_otros_cobros', 'fin_otros_pagos'),
    '57': ('fin_otros_cobros', 'fin_otros_pagos'),
    '58': ('fin_otros_cobros', 'fin_otros_pagos'),
}
EFE_DEFAULT = ('op_otros_cobros', 'op_otros_pagos')

# Conciliacion del resultado neto con el efectivo de operacion.
# Ajustes: movimiento deudor neto del periodo de estas cuentas de gasto.
EFE_ADJ_DEPRECIATION = ['681', '682', '683']
EFE_ADJ_SOCIAL_BENEFITS = ['629']
EFE_ADJ_PROVISIONS = ['684', '685', '686']
# Cambios en activos y pasivos de operacion: -(saldo final - saldo inicial).
EFE_WORKING_CAPITAL = [
    ('wc_cxc_com', ['12']),
    ('wc_cxc_vinc', ['13']),
    ('wc_otras_cxc', ['14', '16', '17', '19']),
    ('wc_exist', ['20', '21', '22', '23', '24', '25', '26', '27', '28', '29']),
    ('wc_gpa', ['18']),
    ('wc_cxp_com', ['42']),
    ('wc_cxp_vinc', ['43']),
    ('wc_otras_cxp', ['40', '41', '46', '47', '48']),
]

# ---------------------------------------------------------------------------
# 3.19 - Estado de Cambios en el Patrimonio Neto: columnas y sus cuentas.
# Resultados acumulados incluye ademas los resultados (clases 6-9) no
# cerrados contra la 59, igual que el 3.1.
# ---------------------------------------------------------------------------
ECPN_COLUMNS = [
    ('capital', ['50']),
    ('capital_adic', ['52']),
    ('acciones_inv', ['51']),
    ('exced_reval', ['57']),
    ('reserva_legal', ['58']),
    ('otras_reservas', ['56']),
    ('res_acum', ['59', '89']),
]

# ---------------------------------------------------------------------------
# 3.20 - Estado de Resultados por Funcion: prefijo -> linea (gana el mas
# largo). Las cuentas por naturaleza 60-68 y la 79 (cargas imputables) que
# no tengan linea propia caen en "otros gastos": su neto es justamente lo
# NO destinado a la clase 9, asi la utilidad neta siempre es la real.
# CONFIRMAR / AJUSTAR con contabilidad segun su esquema de destinos.
# 91, 92 y 93: gastos de distribucion (confirmado por contabilidad, 19/10/2026).
# ---------------------------------------------------------------------------
FUNCTION_MAP = {
    '70': 'ventas',
    '74': 'ventas',             # descuentos concedidos
    '73': 'otros_ing_op',
    '75': 'otros_ing_op',
    '69': 'costo_ventas',
    '90': 'costo_ventas',
    '91': 'gastos_distribucion',
    '92': 'gastos_distribucion',
    '93': 'gastos_distribucion',
    '94': 'gastos_adm',
    '95': 'gastos_venta',
    '77': 'ingresos_fin',
    '97': 'gastos_fin',
    '71': 'otros_ingresos',
    '72': 'otros_ingresos',
    '76': 'otros_ingresos',
    '78': 'otros_ingresos',
    '87': 'participaciones',
    '88': 'impuesto_renta',
}
FUNCTION_DEFAULT = 'otros_gastos'


def _match_prefix(code, mapping):
    """Valor del prefijo mas largo de `mapping` con el que empieza `code`."""
    for length in (4, 3, 2):
        value = mapping.get(code[:length])
        if value is not None:
            return value
    return None


class PleReportInvBalBook0317To0320(models.Model):
    """Formatos 3.17 a 3.20 del Libro de Inventarios y Balances.

    Todos trabajan sobre el periodo [date_start, date_end]:
    - Saldos iniciales "despues de la apertura": saldo al dia anterior a
      date_start mas los asientos de los diarios de cierre/apertura que
      caen dentro del periodo (la reapertura de saldos no es movimiento).
    - Movimientos del periodo sin esos asientos ni el cierre de date_end.
    - Saldos finales antes del cierre de date_end (igual que 3.1 a 3.16).
    """

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_17(self):
        """Formato 3.17 - Balance de comprobacion."""
        return self._generate_single('17')

    def _prepare_report_17(self):
        self.ensure_one()
        return InvBal317ReportExcel(self, self._get_data_17())

    def action_generate_18(self):
        """Formato 3.18 - Estado de flujos de efectivo."""
        return self._generate_single('18')

    def _prepare_report_18(self):
        self.ensure_one()
        return InvBal318ReportExcel(self, self._get_data_18())

    def action_generate_19(self):
        """Formato 3.19 - Estado de cambios en el patrimonio neto."""
        return self._generate_single('19')

    def _prepare_report_19(self):
        self.ensure_one()
        return InvBal319ReportExcel(self, self._get_data_19())

    def action_generate_20(self):
        """Formato 3.20 - Estado de resultados por funcion."""
        return self._generate_single('20')

    def _prepare_report_20(self):
        self.ensure_one()
        return InvBal320ReportExcel(self, self._get_data_20())

    # ------------------------------------------------------------------
    # DATA - Formato 3.17 Balance de comprobacion
    # ------------------------------------------------------------------
    def _get_data_17(self):
        """Balance de comprobacion por subcuenta (4 digitos).

        Columnas de clasificacion: cuentas de balance (clases 1-5 y la 89)
        en Activo / Pasivo y Patrimonio; cuentas de resultados en Perdidas /
        Ganancias. La clase 9 (costos por funcion) y la 79 (su contrapartida)
        no se clasifican porque se anulan entre si.
        """
        self.ensure_one()
        initial = self._period_initial_balances()
        movements = self._period_movements()
        account_ids = set(initial) | set(movements)
        codes = self._codes_by_account_id(account_ids)
        names = {
            a.id: a.name or ''
            for a in self.env['account.account'].with_company(self.company_id).browse(list(account_ids))
        }

        groups = {}
        for account_id in account_ids:
            code = codes.get(account_id, '')
            if not code:
                continue
            key = code[:4]
            group = groups.setdefault(key, {
                'code': key, 'first_code': code, 'name': names.get(account_id, ''),
                'initial': 0.0, 'debit': 0.0, 'credit': 0.0,
            })
            if code < group['first_code']:
                group['first_code'] = code
                group['name'] = names.get(account_id, '')
            debit, credit = movements.get(account_id, (0.0, 0.0))
            group['initial'] += initial.get(account_id, 0.0)
            group['debit'] += debit
            group['credit'] += credit

        lines = []
        for key in sorted(groups):
            group = groups[key]
            final = group['initial'] + group['debit'] - group['credit']
            if all(abs(v) < 0.005 for v in (group['initial'], group['debit'], group['credit'])):
                continue
            row = {
                'code': group['code'],
                'name': group['name'],
                'init_debit': max(group['initial'], 0.0),
                'init_credit': max(-group['initial'], 0.0),
                'mov_debit': group['debit'],
                'mov_credit': group['credit'],
                'final_debit': max(final, 0.0),
                'final_credit': max(-final, 0.0),
                'bg_asset': 0.0, 'bg_liability': 0.0,
                'pl_loss': 0.0, 'pl_gain': 0.0,
            }
            if self._is_pl_code(key):
                if not (key.startswith('9') or key.startswith('79')):
                    row['pl_loss'] = max(final, 0.0)
                    row['pl_gain'] = max(-final, 0.0)
            else:
                row['bg_asset'] = max(final, 0.0)
                row['bg_liability'] = max(-final, 0.0)
            lines.append(row)

        numeric = ['init_debit', 'init_credit', 'mov_debit', 'mov_credit',
                   'final_debit', 'final_credit', 'bg_asset', 'bg_liability',
                   'pl_loss', 'pl_gain']
        totals = {k: sum(r[k] for r in lines) for k in numeric}

        result = {k: 0.0 for k in ('bg_asset', 'bg_liability', 'pl_loss', 'pl_gain')}
        bg_diff = totals['bg_asset'] - totals['bg_liability']
        if bg_diff >= 0:
            result['bg_liability'] = bg_diff      # utilidad
        else:
            result['bg_asset'] = -bg_diff         # perdida
        pl_diff = totals['pl_gain'] - totals['pl_loss']
        if pl_diff >= 0:
            result['pl_loss'] = pl_diff
        else:
            result['pl_gain'] = -pl_diff
        if abs(bg_diff - pl_diff) >= 0.01:
            _logger.warning(
                'PLE Inv. y Balances 3.17 (%s): el resultado del balance (%.2f) '
                'no coincide con el de resultados (%.2f). Revisar destinos 9x/79.',
                self.company_id.name, bg_diff, pl_diff,
            )

        grand = dict(totals)
        for k, v in result.items():
            grand[k] += v
        return {'lines': lines, 'totals': totals, 'result': result, 'grand_totals': grand}

    # ------------------------------------------------------------------
    # DATA - Formato 3.18 Estado de flujos de efectivo
    # ------------------------------------------------------------------
    def _get_data_18(self):
        """Flujos de efectivo del periodo por el metodo directo, con la
        conciliacion del resultado neto (metodo indirecto). En la
        conciliacion, "Otros" cuadra contra el flujo de operacion directo.
        """
        self.ensure_one()
        cash_accounts = self._get_accounts_by_prefix(['10'])
        values = {}

        if cash_accounts:
            self.env.cr.execute("""
                WITH cash_moves AS (
                    SELECT DISTINCT aml.move_id
                      FROM account_move_line aml
                      JOIN account_move am ON am.id = aml.move_id
                     WHERE am.company_id = %(company)s
                       AND am.state = 'posted'
                       AND am.date >= %(date_from)s
                       AND am.date <= %(date_to)s
                       AND am.id NOT IN %(excluded)s
                       AND aml.account_id IN %(cash)s
                )
                SELECT aml.account_id, COALESCE(SUM(-aml.balance), 0.0)
                  FROM account_move_line aml
                 WHERE aml.move_id IN (SELECT move_id FROM cash_moves)
                   AND aml.account_id NOT IN %(cash)s
                 GROUP BY aml.account_id
            """, {
                'company': self.company_id.id,
                'date_from': self.date_start,
                'date_to': self.date_end,
                'excluded': self._period_excluded_move_ids(),
                'cash': tuple(cash_accounts.ids),
            })
            flows = {aid: float(amount or 0.0) for aid, amount in self.env.cr.fetchall()}
            codes = self._codes_by_account_id(flows)
            for account_id, amount in flows.items():
                if abs(amount) < 0.005:
                    continue
                inflow_key, outflow_key = _match_prefix(codes.get(account_id, ''), EFE_MAP) or EFE_DEFAULT
                key = inflow_key if amount > 0 else outflow_key
                values[key] = values.get(key, 0.0) + amount

        def v(key):
            return values.get(key, 0.0)

        op_total = sum(v(k) for k in (
            'op_cobro_ventas', 'op_cobro_regalias', 'op_cobro_intereses', 'op_otros_cobros',
            'op_pago_proveedores', 'op_pago_remuneraciones', 'op_pago_tributos',
            'op_pago_intereses', 'op_otros_pagos'))
        inv_total = sum(v(k) for k in (
            'inv_cobro_valores', 'inv_cobro_ime', 'inv_cobro_intang', 'inv_otros_cobros',
            'inv_pago_valores', 'inv_pago_ime', 'inv_pago_intang', 'inv_otros_pagos'))
        fin_total = sum(v(k) for k in (
            'fin_cobro_acciones', 'fin_cobro_obligaciones', 'fin_otros_cobros',
            'fin_pago_obligaciones', 'fin_pago_dividendos', 'fin_otros_pagos'))
        net_change = op_total + inv_total + fin_total

        initial = self._period_initial_balances()
        cash_initial = sum(initial.get(a.id, 0.0) for a in cash_accounts)
        cash_final_books = sum(
            self._balances_by_account(self.date_end, cash_accounts.ids).values()
        ) if cash_accounts else 0.0
        cash_final = cash_initial + net_change
        if abs(cash_final - cash_final_books) >= 0.01:
            _logger.warning(
                'PLE Inv. y Balances 3.18 (%s): saldo final de efectivo %.2f '
                'difiere del contable %.2f.', self.company_id.name, cash_final,
                cash_final_books,
            )

        # --- Conciliacion (metodo indirecto) ---
        movements = self._period_movements()
        codes = self._codes_by_account_id(set(movements) | set(initial))
        net_mov_by_code = {}
        for account_id, (debit, credit) in movements.items():
            code = codes.get(account_id, '')
            net_mov_by_code[code] = net_mov_by_code.get(code, 0.0) + debit - credit
        net_result = self._period_net_result(movements, codes)

        final_balances = self._balances_by_account(self.date_end)
        final_codes = self._codes_by_account_id(final_balances)
        codes.update(final_codes)
        delta_by_code = {}
        for account_id in set(initial) | set(final_balances):
            code = codes.get(account_id, '')
            delta = final_balances.get(account_id, 0.0) - initial.get(account_id, 0.0)
            delta_by_code[code] = delta_by_code.get(code, 0.0) + delta

        depreciation = self._sum_by_prefix(net_mov_by_code, EFE_ADJ_DEPRECIATION)
        social_benefits = self._sum_by_prefix(net_mov_by_code, EFE_ADJ_SOCIAL_BENEFITS)
        provisions = self._sum_by_prefix(net_mov_by_code, EFE_ADJ_PROVISIONS)
        working_capital = {
            key: -self._sum_by_prefix(delta_by_code, prefixes)
            for key, prefixes in EFE_WORKING_CAPITAL
        }
        others = op_total - (net_result + depreciation + social_benefits
                             + provisions + sum(working_capital.values()))

        values.update({
            'op_total': op_total, 'inv_total': inv_total, 'fin_total': fin_total,
            'net_change': net_change, 'cash_initial': cash_initial,
            'cash_final': cash_final, 'net_result': net_result,
            'adj_depreciation': depreciation, 'adj_social_benefits': social_benefits,
            'adj_provisions': provisions, 'adj_others': others,
        })
        values.update(working_capital)
        return values

    # ------------------------------------------------------------------
    # DATA - Formato 3.19 Estado de cambios en el patrimonio neto
    # ------------------------------------------------------------------
    def _get_data_19(self):
        """Saldos inicial y final por columna de patrimonio y movimientos
        del periodo. Fila 10 = utilidad neta del periodo (en resultados
        acumulados). El resto del movimiento de cada columna va a:
        4 (aportes) o 9 (reducciones) en capital, capital adicional y
        acciones de inversion; 7 en excedente de revaluacion; 11 en las
        demas. Asi el saldo final siempre es el contable.
        """
        self.ensure_one()
        initial = self._period_initial_balances()
        final = self._balances_by_account(self.date_end)
        codes = self._codes_by_account_id(set(initial) | set(final))
        net_result = self._period_net_result()

        def column_balance(balances, prefixes, include_pl):
            total = 0.0
            for account_id, amount in balances.items():
                code = codes.get(account_id, '')
                if any(code.startswith(p) for p in prefixes) or (include_pl and self._is_pl_code(code)):
                    total += amount
            return -total

        columns = {}
        for key, prefixes in ECPN_COLUMNS:
            include_pl = key == 'res_acum'
            ini = column_balance(initial, prefixes, include_pl)
            fin = column_balance(final, prefixes, include_pl)
            rows = {}
            movement = fin - ini
            if key == 'res_acum':
                rows['10'] = net_result
                movement -= net_result
            if abs(movement) >= 0.005:
                if key in ('capital', 'capital_adic', 'acciones_inv'):
                    rows['4' if movement > 0 else '9'] = movement
                elif key == 'exced_reval':
                    rows['7'] = movement
                else:
                    rows['11'] = movement
            columns[key] = {'initial': ini, 'final': fin, 'rows': rows}
        return {'columns': columns, 'net_result': net_result}

    # ------------------------------------------------------------------
    # DATA - Formato 3.20 Estado de resultados por funcion
    # ------------------------------------------------------------------
    def _get_data_20(self):
        """Estado de resultados por funcion del periodo. Ingresos en
        positivo y gastos en negativo; la utilidad neta coincide con la del
        3.18 y la fila 10 del 3.19."""
        self.ensure_one()
        movements = self._period_movements()
        codes = self._codes_by_account_id(movements)
        values = {}
        for account_id, (debit, credit) in movements.items():
            code = codes.get(account_id, '')
            if not self._is_pl_code(code):
                continue
            key = _match_prefix(code, FUNCTION_MAP) or FUNCTION_DEFAULT
            values[key] = values.get(key, 0.0) - (debit - credit)

        def v(key):
            return values.get(key, 0.0)

        total_ingresos = v('ventas') + v('otros_ing_op')
        utilidad_bruta = total_ingresos + v('costo_ventas')
        utilidad_operativa = (utilidad_bruta + v('gastos_adm') + v('gastos_venta')
                              + v('gastos_distribucion'))
        antes_part = (utilidad_operativa + v('ingresos_fin') + v('gastos_fin')
                      + v('otros_ingresos') + v('otros_gastos'))
        antes_extra = antes_part + v('participaciones') + v('impuesto_renta')
        utilidad_neta = antes_extra
        values.update({
            'total_ingresos': total_ingresos,
            'utilidad_bruta': utilidad_bruta,
            'utilidad_operativa': utilidad_operativa,
            'antes_part': antes_part,
            'antes_extra': antes_extra,
            'antes_minoritario': antes_extra,
            'utilidad_neta': utilidad_neta,
            'utilidad_atribuible': utilidad_neta,
        })
        return values

    # ------------------------------------------------------------------
    # Helpers del grupo (solo los usan estos formatos)
    # ------------------------------------------------------------------
    def _period_excluded_move_ids(self):
        """Asientos que no son movimiento del periodo: cierres/aperturas
        dentro del periodo + cierre de la fecha fin."""
        self.ensure_one()
        ids = set(self._get_period_closing_opening_move_ids())
        ids |= set(self._get_excluded_move_ids())
        ids.discard(0)
        return tuple(ids) or (0,)

    def _period_initial_balances(self):
        """Saldo inicial por account_id "despues de la apertura": saldo al
        dia anterior a date_start + lineas de los asientos de cierre/apertura
        del periodo (excepto el cierre de date_end, que no se considera)."""
        self.ensure_one()
        balances = self._balances_by_account(self.date_start - timedelta(days=1))
        adjust_ids = set(self._get_period_closing_opening_move_ids())
        adjust_ids -= set(self._get_excluded_move_ids())
        adjust_ids.discard(0)
        if adjust_ids:
            self.env.cr.execute("""
                SELECT account_id, COALESCE(SUM(debit - credit), 0.0)
                  FROM account_move_line
                 WHERE move_id IN %(moves)s
                 GROUP BY account_id
            """, {'moves': tuple(adjust_ids)})
            for account_id, amount in self.env.cr.fetchall():
                balances[account_id] = balances.get(account_id, 0.0) + float(amount or 0.0)
        return balances

    def _period_movements(self):
        """Movimientos del periodo por account_id: {id: (debe, haber)}."""
        self.ensure_one()
        self.env.cr.execute("""
            SELECT aml.account_id,
                   COALESCE(SUM(aml.debit), 0.0),
                   COALESCE(SUM(aml.credit), 0.0)
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND am.date >= %(date_from)s
               AND am.date <= %(date_to)s
               AND am.id NOT IN %(excluded)s
             GROUP BY aml.account_id
        """, {
            'company': self.company_id.id,
            'date_from': self.date_start,
            'date_to': self.date_end,
            'excluded': self._period_excluded_move_ids(),
        })
        return {
            account_id: (float(debit or 0.0), float(credit or 0.0))
            for account_id, debit, credit in self.env.cr.fetchall()
        }

    def _codes_by_account_id(self, account_ids):
        """{account_id: codigo} resuelto para la compania del reporte."""
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).browse(list(account_ids))
        return {a.id: a.code or '' for a in accounts}

    def _sum_by_prefix(self, amounts_by_code, prefixes):
        return sum(
            amount for code, amount in amounts_by_code.items()
            if any(code.startswith(p) for p in prefixes)
        )

    def _period_net_result(self, movements=None, codes=None):
        """Utilidad (+) o perdida (-) del periodo: -(debe - haber) de las
        cuentas de resultados, sin cierres/aperturas ni la 89."""
        self.ensure_one()
        movements = movements if movements is not None else self._period_movements()
        codes = codes if codes is not None else self._codes_by_account_id(movements)
        return -sum(
            debit - credit for account_id, (debit, credit) in movements.items()
            if self._is_pl_code(codes.get(account_id, ''))
        )
