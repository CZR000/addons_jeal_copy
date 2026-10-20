import logging
from datetime import timedelta

from odoo import models

from ..reports.report_inv_bal_0301 import InvBal31ReportExcel

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0301(models.Model):
    """Formato 3.1 (Balance General) del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_01(self):
        """Formato 3.1 - Balance General."""
        return self._generate_single('01')

    def _prepare_report_01(self):
        self.ensure_one()
        return InvBal31ReportExcel(self, self._get_data_01())

    # ------------------------------------------------------------------
    # DATA - Formato 3.1 Balance General
    # ------------------------------------------------------------------
    #
    # MAPEO DE CUENTAS (PCGE 2019) -> LINEA DEL BALANCE
    # ------------------------------------------------------------------
    # Cada clave agrupa los prefijos (2 o 3 digitos) que suman en esa linea.
    # Gana el prefijo mas especifico: 396 va a intangibles aunque 39 este
    # en inmuebles, maquinaria y equipo.
    # Las cuentas de balance (clases 1 a 5) cuyo prefijo no este en el
    # mapa caen en la linea "otros" de su clase (BALANCE_FALLBACK), y el
    # resultado (clases 6 a 9) se calcula aparte, para que el balance
    # siempre cuadre: TOTAL ACTIVO = TOTAL PASIVO Y PATRIMONIO NETO.
    BALANCE_MAP = {
        # --- ACTIVO ---
        'caja':            ['10'],
        'val_neg':         ['11'],
        'cxc_com':         ['12', '19'],
        'cxc_vinc':        ['13'],
        'otras_cxc':       ['14', '16', '17'],
        'exist':           ['20', '21', '22', '23', '24', '25', '26', '28', '29'],
        'gpa':             ['18'],
        'cxc_lp':          [],
        'cxc_vinc_lp':     [],
        'otras_cxc_lp':    [],
        'inv_perm':        ['30', '31', '367'],        # 367 desvalorizacion inv. mobiliarias
        'ime':             ['32', '33', '36', '39'],   # 36 y 39 restan por signo
        'intang':          ['34', '365', '396'],       # 365 desvaloriz. / 396 amortiz. intangibles
        'ir_dif_act':      ['37'],
        'otros_act':       ['27', '35', '366', '38'],  # 35 activos biologicos
        # --- PASIVO ---
        'sobregiros':      ['45'],
        'cxp_com':         ['42'],
        'cxp_vinc':        ['43'],
        'otras_cxp':       ['40', '41', '44', '46', '47', '48'],
        'parte_cte_lp':    [],
        'deudas_lp':       [],
        'cxp_vinc_lp':     [],
        'ing_dif':         ['49'],
        'ir_dif_pas':      [],
        # --- PATRIMONIO ---
        'capital':         ['50'],
        'acciones_inv':    ['51'],
        'capital_adic':    ['52'],
        'otras_reservas':  ['56'],
        'exced_reval':     ['57'],
        'reservas_leg':    ['58'],
        'resultados_acum': ['59', '89'],     # 89: puente del cierre
    }

    # Clase de la cuenta -> linea donde cae si su prefijo no esta mapeado.
    BALANCE_FALLBACK = {
        '1': 'otros_act', '2': 'otros_act', '3': 'otros_act',
        '4': 'otras_cxp',
        '5': 'otras_reservas',
    }

    # Lineas de PASIVO / PATRIMONIO: su saldo natural es acreedor, por lo
    # que se muestran como (credito - debito).
    LIABILITY_KEYS = {
        'sobregiros', 'cxp_com', 'cxp_vinc', 'otras_cxp', 'parte_cte_lp',
        'deudas_lp', 'cxp_vinc_lp', 'ing_dif', 'ir_dif_pas',
        'capital', 'capital_adic', 'acciones_inv', 'exced_reval',
        'reservas_leg', 'otras_reservas', 'resultados_acum',
    }

    def _get_data_01(self):
        """Devuelve la estructura del Balance General (columnas ACTIVO y
        PASIVO Y PATRIMONIO) con los saldos al `date_end`.

        Retorna dict con:
            'activo':  lista de filas (tipo, label, valor)
            'pasivo':  lista de filas (tipo, label, valor)
        Tipos de fila: 'section', 'line', 'total', 'blank'.
        """
        self.ensure_one()
        bal = self._account_balances_as_of(self.date_end)
        totals, unmapped = self._classify_balance_accounts(bal)
        if unmapped:
            _logger.warning(
                'PLE Inv. y Balances 3.1 (%s): prefijos sin linea propia, '
                'agrupados en "otros": %s',
                self.company_id.name, ', '.join(unmapped),
            )

        def v(key):
            total = totals.get(key, 0.0)
            return -total if key in self.LIABILITY_KEYS else total

        # --- Resultado: ejercicio actual y ejercicios anteriores no cerrados ---
        fy_start = self.company_id.compute_fiscalyear_dates(self.date_end)['date_from']
        bal_prev = self._account_balances_as_of(fy_start - timedelta(days=1))
        pl_total = sum(a for c, a in bal.items() if self._is_pl_code(c))
        pl_prev = sum(a for c, a in bal_prev.items() if self._is_pl_code(c))
        resultado_ejercicio = -(pl_total - pl_prev)

        # --- Columna ACTIVO ---
        caja, val_neg = v('caja'), v('val_neg')
        cxc_com, cxc_vinc, otras_cxc = v('cxc_com'), v('cxc_vinc'), v('otras_cxc')
        exist, gpa = v('exist'), v('gpa')
        tac = caja + val_neg + cxc_com + cxc_vinc + otras_cxc + exist + gpa

        cxc_lp, cxc_vinc_lp, otras_cxc_lp = v('cxc_lp'), v('cxc_vinc_lp'), v('otras_cxc_lp')
        inv_perm, ime, intang = v('inv_perm'), v('ime'), v('intang')
        ir_dif_act, otros_act = v('ir_dif_act'), v('otros_act')
        tanc = (cxc_lp + cxc_vinc_lp + otras_cxc_lp + inv_perm + ime
                + intang + ir_dif_act + otros_act)

        activo = [
            ('section', 'ACTIVO', None),
            ('section', 'ACTIVO CORRIENTE', None),
            ('line', 'Caja y Bancos', caja),
            ('line', 'Valores Negociables', val_neg),
            ('line', 'Cuentas por Cobrar Comerciales', cxc_com),
            ('line', 'Cuentas por Cobrar a Vinculadas', cxc_vinc),
            ('line', 'Otras Cuentas por Cobrar', otras_cxc),
            ('line', 'Existencias', exist),
            ('line', 'Gastos Pagados por Anticipado', gpa),
            ('total', 'TOTAL ACTIVO CORRIENTE', tac),
            ('blank', '', None),
            ('section', 'ACTIVO NO CORRIENTE', None),
            ('line', 'Cuentas por Cobrar a Largo Plazo', cxc_lp),
            ('line', 'Cuentas por Cobrar a Vinculadas a Largo Plazo', cxc_vinc_lp),
            ('line', 'Otras Cuentas por Cobrar a Largo Plazo', otras_cxc_lp),
            ('line', 'Inversiones Permanentes', inv_perm),
            ('line', 'Inmuebles, Maquinaria y Equipo (neto de depreciacion acumulada)', ime),
            ('line', 'Activos Intangibles (neto de amortizacion acumulada)', intang),
            ('line', 'Impuesto a la Renta y Participaciones Diferidos Activo', ir_dif_act),
            ('line', 'Otros Activos', otros_act),
            ('total', 'TOTAL ACTIVO NO CORRIENTE', tanc),
            ('blank', '', None),
            ('total', 'TOTAL ACTIVO', tac + tanc),
        ]

        # --- Columna PASIVO Y PATRIMONIO ---
        sobregiros, cxp_com, cxp_vinc = v('sobregiros'), v('cxp_com'), v('cxp_vinc')
        otras_cxp, parte_cte_lp = v('otras_cxp'), v('parte_cte_lp')
        tpc = sobregiros + cxp_com + cxp_vinc + otras_cxp + parte_cte_lp

        deudas_lp, cxp_vinc_lp = v('deudas_lp'), v('cxp_vinc_lp')
        ing_dif, ir_dif_pas = v('ing_dif'), v('ir_dif_pas')
        tpnc = deudas_lp + cxp_vinc_lp + ing_dif + ir_dif_pas
        total_pasivo = tpc + tpnc

        capital, capital_adic = v('capital'), v('capital_adic')
        acciones_inv, exced_reval = v('acciones_inv'), v('exced_reval')
        reservas_leg, otras_reservas = v('reservas_leg'), v('otras_reservas')
        # Resultados acumulados = cuenta 59 + resultados de ejercicios
        # anteriores que no se hayan cerrado contra la 59.
        resultados_acum = v('resultados_acum') - pl_prev
        total_patrimonio = (capital + capital_adic + acciones_inv + exced_reval
                            + reservas_leg + otras_reservas + resultados_acum
                            + resultado_ejercicio)

        pasivo = [
            ('section', 'PASIVO Y PATRIMONIO', None),
            ('section', 'PASIVO CORRIENTE', None),
            ('line', 'Sobregiros y Pagares Bancarios', sobregiros),
            ('line', 'Cuentas por Pagar Comerciales', cxp_com),
            ('line', 'Cuentas por Pagar a Vinculadas', cxp_vinc),
            ('line', 'Otras Cuentas por Pagar', otras_cxp),
            ('line', 'Parte Corriente de las Deudas a Largo Plazo', parte_cte_lp),
            ('total', 'TOTAL PASIVO CORRIENTE', tpc),
            ('blank', '', None),
            ('section', 'PASIVO NO CORRIENTE', None),
            ('line', 'Deudas a Largo Plazo', deudas_lp),
            ('line', 'Cuentas por Pagar a Vinculadas', cxp_vinc_lp),
            ('line', 'Ingresos Diferidos', ing_dif),
            ('line', 'Impuesto a la Renta y Participaciones Diferidos Pasivo', ir_dif_pas),
            ('total', 'TOTAL PASIVO NO CORRIENTE', tpnc),
            ('blank', '', None),
            ('total', 'TOTAL PASIVO', total_pasivo),
            ('blank', '', None),
            ('section', 'PATRIMONIO NETO', None),
            ('line', 'Capital', capital),
            ('line', 'Capital Adicional', capital_adic),
            ('line', 'Acciones de Inversion', acciones_inv),
            ('line', 'Excedentes de Revaluacion', exced_reval),
            ('line', 'Reservas Legales', reservas_leg),
            ('line', 'Otras Reservas', otras_reservas),
            ('line', 'Resultados Acumulados', resultados_acum),
            ('line', 'Resultado del Ejercicio', resultado_ejercicio),
            ('total', 'TOTAL PATRIMONIO NETO', total_patrimonio),
            ('blank', '', None),
            ('total', 'TOTAL PASIVO Y PATRIMONIO NETO', total_pasivo + total_patrimonio),
        ]

        return {'activo': activo, 'pasivo': pasivo}

    def _classify_balance_accounts(self, balances):
        """Agrupa los saldos de las cuentas de balance (clases 1 a 5) por
        clave de BALANCE_MAP. Retorna ({clave: saldo}, [prefijos sin mapear]).
        """
        prefix_to_key = {}
        for key, prefixes in self.BALANCE_MAP.items():
            for prefix in prefixes:
                prefix_to_key[prefix] = key

        totals = {key: 0.0 for key in self.BALANCE_MAP}
        unmapped = set()
        for code, amount in balances.items():
            key = prefix_to_key.get(code[:3]) or prefix_to_key.get(code[:2])
            if not key:
                account_class = code[:1]
                if account_class not in self.BALANCE_FALLBACK:
                    continue
                key = self.BALANCE_FALLBACK[account_class]
                unmapped.add(code[:2])
            totals[key] += amount
        return totals, sorted(unmapped)
