import base64
import logging
import os
import subprocess
import tempfile
from calendar import monthrange
from datetime import date, timedelta
from io import BytesIO

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..reports.report_inv_bal_31 import InvBal31ReportExcel
from ..reports.report_inv_bal_base import xlsxwriter

_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Catalogo de formatos del Libro de Inventarios y Balances.
# El sufijo de dos digitos (01..20) se usa en los nombres de campo y de
# accion: xls_binary_<nn>, pdf_binary_<nn>, action_generate_<nn>.
# ---------------------------------------------------------------------------
FORMATOS = [
    ('01', '3.1',  'Balance General'),
    ('02', '3.2',  'Efectivo y Equivalente al Efectivo (Cuenta 10)'),
    ('03', '3.3',  'Clientes (Cuenta 12)'),
    ('04', '3.4',  'Cuentas por Cobrar a Accionistas (Socios) y Personal (Cuenta 14)'),
    ('05', '3.5',  'Cuentas por Cobrar Diversas (Cuenta 16)'),
    ('06', '3.6',  'Estimacion de Cuentas de Cobranza Dudosa (Cuenta 19)'),
    ('07', '3.7',  'Mercaderias y Productos Terminados (Cuentas 20 y 21)'),
    ('08', '3.8',  'Valores (Cuenta 31)'),
    ('09', '3.9',  'Intangibles (Cuenta 34)'),
    ('10', '3.10', 'Tributos por Pagar (Cuenta 40)'),
    ('11', '3.11', 'Remuneraciones y Participaciones por Pagar (Cuenta 41)'),
    ('12', '3.12', 'Proveedores (Cuenta 42)'),
    ('13', '3.13', 'Cuentas por Pagar Diversas - Terceros y Relacionadas (Cuentas 46 y 47)'),
    ('14', '3.14', 'Beneficios Sociales de los Trabajadores (Cuenta 47)'),
    ('15', '3.15', 'Ganancias Diferidas (Cuenta 49)'),
    ('17', '3.17', 'Balance de Comprobacion (Anexo 1)'),
    ('18', '3.18', 'Estado de Flujos de Efectivo'),
    ('19', '3.19', 'Estado de Cambios en el Patrimonio Neto'),
    ('20', '3.20', 'Estado de Ganancias y Perdidas por Funcion'),
]

MONTHS = [
    ('01', 'Enero'), ('02', 'Febrero'), ('03', 'Marzo'), ('04', 'Abril'),
    ('05', 'Mayo'), ('06', 'Junio'), ('07', 'Julio'), ('08', 'Agosto'),
    ('09', 'Septiembre'), ('10', 'Octubre'), ('11', 'Noviembre'),
    ('12', 'Diciembre'),
]

# Alcance del periodo para date_start:
#   'month' -> date_start = primer dia del mes seleccionado (saldo inicial del
#              mes + movimientos del mes en 3.17 a 3.20).
#   'year'  -> date_start = 01/01 del anio seleccionado (acumulado del
#              ejercicio, como el libro oficial al 31/12).
# date_end siempre es el ultimo dia del mes seleccionado.
PERIOD_SCOPE = 'month'


def _default_period(env):
    """Ultimo dia del mes anterior a la fecha actual (periodo por defecto)."""
    today = fields.Date.context_today(env.user)
    return today.replace(day=1) - timedelta(days=1)


class PleReportInvBal(models.Model):
    _name = 'ple.report.inv.bal.book'
    _description = 'Reporte PLE Libro de Inventarios y Balances - Fisico (3.1 a 3.20)'
    _order = 'period_year desc, period_month desc, id desc'

    _sql_constraints = [
        ('period_company_uniq',
         'unique(company_id, period_year, period_month)',
         'Ya existe un reporte para esta compañía y período.'),
    ]

    name = fields.Char(compute='_compute_name', store=True, string='Nombre')
    company_id = fields.Many2one(
        'res.company', string='Compania',
        required=True, default=lambda self: self.env.company,
        domain=lambda self: [('id', 'in', self.env.user.company_ids.ids)],
    )
    period_month = fields.Selection(
        MONTHS, string='Mes', required=True,
        default=lambda self: _default_period(self.env).strftime('%m'),
    )
    period_year = fields.Selection(
        selection='_get_year_selection', string='Año', required=True,
        default=lambda self: str(_default_period(self.env).year),
    )
    # Se calculan del Mes/Año; no se muestran en la vista.
    date_start = fields.Date(
        string='Fecha Inicio', compute='_compute_period_dates', store=True,
    )
    date_end = fields.Date(
        string='Fecha Fin', compute='_compute_period_dates', store=True,
    )
    date_generated = fields.Date(string='Generado el', readonly=True)
    show_by_format = fields.Boolean(
        string='Generar por formato', default=False,
        help='Muestra las secciones de cada formato (3.1 a 3.20) para '
             'generarlos uno por uno.',
    )

    state = fields.Selection(
        selection=[
            ('draft', 'Borrador'),
            ('confirmed', 'Generado'),
        ],
        string='Estado', default='draft', tracking=True,
    )

    closing_journal_ids = fields.Many2many(
        'account.journal', 'ple_inv_bal_book_closing_journal_rel',
        'report_id', 'journal_id',
        string='Diarios de cierre',
        compute='_compute_closing_opening_journals', store=True, readonly=False,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        help='Asientos de cierre del ejercicio. Los de estos diarios con fecha '
             'igual a la Fecha Fin no se consideran, para mostrar los saldos '
             'antes del cierre. En los estados del periodo (3.18 a 3.20) '
             'tampoco se consideran los que caen dentro del periodo.',
    )
    opening_journal_ids = fields.Many2many(
        'account.journal', 'ple_inv_bal_book_opening_journal_rel',
        'report_id', 'journal_id',
        string='Diarios de apertura',
        compute='_compute_closing_opening_journals', store=True, readonly=False,
        domain="[('company_id', '=', company_id), ('type', '=', 'general')]",
        help='Asientos de apertura (reapertura de saldos). En los estados del '
             'periodo (3.17 a 3.20) se tratan como saldo inicial y no como '
             'movimiento, flujo o resultado del periodo.',
    )

    # -- Campos de archivo por formato (Excel y PDF por cada uno de 3.1 a 3.20) --
    xls_filename_01 = fields.Char()
    xls_binary_01 = fields.Binary(string='Excel 3.1', readonly=True)
    pdf_filename_01 = fields.Char()
    pdf_binary_01 = fields.Binary(string='PDF 3.1', readonly=True)
    xls_filename_02 = fields.Char()
    xls_binary_02 = fields.Binary(string='Excel 3.2', readonly=True)
    pdf_filename_02 = fields.Char()
    pdf_binary_02 = fields.Binary(string='PDF 3.2', readonly=True)
    xls_filename_03 = fields.Char()
    xls_binary_03 = fields.Binary(string='Excel 3.3', readonly=True)
    pdf_filename_03 = fields.Char()
    pdf_binary_03 = fields.Binary(string='PDF 3.3', readonly=True)
    xls_filename_04 = fields.Char()
    xls_binary_04 = fields.Binary(string='Excel 3.4', readonly=True)
    pdf_filename_04 = fields.Char()
    pdf_binary_04 = fields.Binary(string='PDF 3.4', readonly=True)
    xls_filename_05 = fields.Char()
    xls_binary_05 = fields.Binary(string='Excel 3.5', readonly=True)
    pdf_filename_05 = fields.Char()
    pdf_binary_05 = fields.Binary(string='PDF 3.5', readonly=True)
    xls_filename_06 = fields.Char()
    xls_binary_06 = fields.Binary(string='Excel 3.6', readonly=True)
    pdf_filename_06 = fields.Char()
    pdf_binary_06 = fields.Binary(string='PDF 3.6', readonly=True)
    xls_filename_07 = fields.Char()
    xls_binary_07 = fields.Binary(string='Excel 3.7', readonly=True)
    pdf_filename_07 = fields.Char()
    pdf_binary_07 = fields.Binary(string='PDF 3.7', readonly=True)
    xls_filename_08 = fields.Char()
    xls_binary_08 = fields.Binary(string='Excel 3.8', readonly=True)
    pdf_filename_08 = fields.Char()
    pdf_binary_08 = fields.Binary(string='PDF 3.8', readonly=True)
    xls_filename_09 = fields.Char()
    xls_binary_09 = fields.Binary(string='Excel 3.9', readonly=True)
    pdf_filename_09 = fields.Char()
    pdf_binary_09 = fields.Binary(string='PDF 3.9', readonly=True)
    xls_filename_10 = fields.Char()
    xls_binary_10 = fields.Binary(string='Excel 3.10', readonly=True)
    pdf_filename_10 = fields.Char()
    pdf_binary_10 = fields.Binary(string='PDF 3.10', readonly=True)
    xls_filename_11 = fields.Char()
    xls_binary_11 = fields.Binary(string='Excel 3.11', readonly=True)
    pdf_filename_11 = fields.Char()
    pdf_binary_11 = fields.Binary(string='PDF 3.11', readonly=True)
    xls_filename_12 = fields.Char()
    xls_binary_12 = fields.Binary(string='Excel 3.12', readonly=True)
    pdf_filename_12 = fields.Char()
    pdf_binary_12 = fields.Binary(string='PDF 3.12', readonly=True)
    xls_filename_13 = fields.Char()
    xls_binary_13 = fields.Binary(string='Excel 3.13', readonly=True)
    pdf_filename_13 = fields.Char()
    pdf_binary_13 = fields.Binary(string='PDF 3.13', readonly=True)
    xls_filename_14 = fields.Char()
    xls_binary_14 = fields.Binary(string='Excel 3.14', readonly=True)
    pdf_filename_14 = fields.Char()
    pdf_binary_14 = fields.Binary(string='PDF 3.14', readonly=True)
    xls_filename_15 = fields.Char()
    xls_binary_15 = fields.Binary(string='Excel 3.15', readonly=True)
    pdf_filename_15 = fields.Char()
    pdf_binary_15 = fields.Binary(string='PDF 3.15', readonly=True)
    xls_filename_17 = fields.Char()
    xls_binary_17 = fields.Binary(string='Excel 3.17', readonly=True)
    pdf_filename_17 = fields.Char()
    pdf_binary_17 = fields.Binary(string='PDF 3.17', readonly=True)
    xls_filename_18 = fields.Char()
    xls_binary_18 = fields.Binary(string='Excel 3.18', readonly=True)
    pdf_filename_18 = fields.Char()
    pdf_binary_18 = fields.Binary(string='PDF 3.18', readonly=True)
    xls_filename_19 = fields.Char()
    xls_binary_19 = fields.Binary(string='Excel 3.19', readonly=True)
    pdf_filename_19 = fields.Char()
    pdf_binary_19 = fields.Binary(string='PDF 3.19', readonly=True)
    xls_filename_20 = fields.Char()
    xls_binary_20 = fields.Binary(string='Excel 3.20', readonly=True)
    pdf_filename_20 = fields.Char()
    pdf_binary_20 = fields.Binary(string='PDF 3.20', readonly=True)

    # -- Libro completo (los 19 formatos en un solo Excel y un solo PDF) --
    xls_filename_all = fields.Char()
    xls_binary_all = fields.Binary(string='Excel Libro Completo', readonly=True)
    pdf_filename_all = fields.Char()
    pdf_binary_all = fields.Binary(string='PDF Libro Completo', readonly=True)

    @api.depends('period_month', 'period_year')
    def _compute_period_dates(self):
        for rec in self:
            year, month = int(rec.period_year or 0), int(rec.period_month or 0)
            if not month or not year:
                rec.date_start = rec.date_end = False
                continue
            rec.date_end = date(year, month, monthrange(year, month)[1])
            rec.date_start = date(year, 1 if PERIOD_SCOPE == 'year' else month, 1)

    @api.model
    def _get_year_selection(self):
        """Anios disponibles: desde 2020 hasta el anio actual, el mas
        reciente primero."""
        current = fields.Date.context_today(self).year
        return [(str(y), str(y)) for y in range(current, 2019, -1)]

    @api.depends('company_id')
    def _compute_closing_opening_journals(self):
        Journal = self.env['account.journal']
        for rec in self:
            if not rec.company_id:
                rec.closing_journal_ids = False
                rec.opening_journal_ids = False
                continue
            base = [('company_id', '=', rec.company_id.id), ('type', '=', 'general')]
            rec.closing_journal_ids = Journal.search(
                base + ['|', ('name', 'ilike', 'cierre'), ('code', '=ilike', 'cier%')]
            )
            rec.opening_journal_ids = Journal.search(
                base + ['|', ('name', 'ilike', 'apertura'), ('code', '=ilike', 'apert%')]
            )

    @api.depends('company_id', 'period_month', 'period_year')
    def _compute_name(self):
        for rec in self:
            if rec.period_month and rec.period_year:
                rec.name = 'Libro Inv. y Balances - %s/%s - %s' % (
                    rec.period_month, rec.period_year,
                    rec.company_id.name or '',
                )
            else:
                rec.name = 'Libro Inventarios y Balances'

    # ------------------------------------------------------------------
    # Acciones por formato
    # ------------------------------------------------------------------
    def action_generate_01(self):
        """Formato 3.1 - Balance General."""
        return self._generate_single('01')

    def _prepare_report_01(self):
        self.ensure_one()
        return InvBal31ReportExcel(self, self._get_data_31())

    def _generate_single(self, nn):
        """Genera Excel + PDF de un formato. Cada formato define
        `_prepare_report_<nn>()` que retorna la instancia del reporte."""
        self.ensure_one()
        self._check_before_generate()
        report = getattr(self, '_prepare_report_%s' % nn)()
        self._store_report(nn, report)
        self._mark_generated()

    def action_generate_all_xls(self):
        """Libro completo en Excel: una hoja por formato (3.1 a 3.20)."""
        self.ensure_one()
        self._check_before_generate()
        xlsx_bytes, xls_name = self._build_consolidated_xlsx()
        self.write({
            'xls_binary_all': base64.b64encode(xlsx_bytes),
            'xls_filename_all': xls_name,
        })
        self._mark_generated()

    def action_generate_all_pdf(self):
        """Libro completo en PDF (una sola conversion con LibreOffice).
        Tambien actualiza el Excel completo, para que ambos archivos
        correspondan siempre a la misma generacion."""
        self.ensure_one()
        self._check_before_generate()
        xlsx_bytes, xls_name = self._build_consolidated_xlsx()
        pdf_bytes = self._xlsx_to_pdf(xlsx_bytes)
        self.write({
            'xls_binary_all': base64.b64encode(xlsx_bytes),
            'xls_filename_all': xls_name,
            'pdf_binary_all': base64.b64encode(pdf_bytes),
            'pdf_filename_all': xls_name.replace('.xlsx', '.pdf'),
        })
        self._mark_generated()

    def _build_consolidated_xlsx(self):
        """Arma el XLSX con los 19 formatos. Si alguno falla, se detiene e
        indica cual. Retorna (bytes, nombre de archivo)."""
        self.ensure_one()
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        for nn, code, title in FORMATOS:
            try:
                report = getattr(self, '_prepare_report_%s' % nn)()
                report.write_sheet(workbook)
            except UserError as err:
                raise UserError(_('Formato %s - %s:\n%s') % (
                    code, title, err.args[0] if err.args else err,
                ))
            except Exception as err:
                _logger.exception(
                    'PLE Inv. y Balances: error en el formato %s (libro completo)',
                    code,
                )
                raise UserError(_(
                    'No se pudo generar el formato %s - %s.\n%s'
                ) % (code, title, err))
        workbook.close()

        safe = ''.join(
            c if c.isalnum() else '_' for c in (self.company_id.name or 'company')
        )
        xls_name = 'Libro_Inv_Bal_Completo_%s_%s.xlsx' % (
            safe, self.date_end.strftime('%Y%m'),
        )
        return output.getvalue(), xls_name

    def action_reset_to_draft(self):
        vals = {
            'state': 'draft', 'date_generated': False,
            'xls_binary_all': False, 'xls_filename_all': False,
            'pdf_binary_all': False, 'pdf_filename_all': False,
        }
        for nn, _code, _title in FORMATOS:
            vals.update({
                'xls_binary_%s' % nn: False,
                'xls_filename_%s' % nn: False,
                'pdf_binary_%s' % nn: False,
                'pdf_filename_%s' % nn: False,
            })
        self.write(vals)

    # ------------------------------------------------------------------
    # Helpers comunes (reutilizados del patron del Libro Caja 1.1)
    # ------------------------------------------------------------------
    def _store_report(self, nn, report):
        """Genera Excel + PDF de un reporte y los guarda en sus campos.

        `report` es una instancia de la clase constructora del formato
        (expone get_content() -> bytes xlsx y get_filename() -> str).
        """
        self.ensure_one()
        xlsx_bytes = report.get_content()
        xls_name = report.get_filename()
        pdf_bytes = self._xlsx_to_pdf(xlsx_bytes)
        pdf_name = xls_name.replace('.xlsx', '.pdf')
        self.write({
            'xls_binary_%s' % nn: base64.b64encode(xlsx_bytes),
            'xls_filename_%s' % nn: xls_name,
            'pdf_binary_%s' % nn: base64.b64encode(pdf_bytes),
            'pdf_filename_%s' % nn: pdf_name,
        })

    def _check_before_generate(self):
        """Validaciones comunes antes de generar cualquier formato 3.x."""
        self.ensure_one()
        self._check_company_access()
        self._check_dates()

    def _check_company_access(self):
        """La compania del registro debe estar activa en el selector de
        companias del usuario (env.companies)."""
        self.ensure_one()
        if self.company_id not in self.env.companies:
            raise UserError(_(
                'No es posible generar el reporte para la compañía seleccionada. '
                'Verifique que la compañía esté activa en el selector de compañías.'
            ))

    def _check_dates(self):
        self.ensure_one()
        if not self.date_start or not self.date_end:
            raise UserError(_('Debe indicar el Mes y el Año del reporte.'))

    def _mark_generated(self):
        self.write({
            'date_generated': fields.Date.context_today(self),
            'state': 'confirmed',
        })

    def _xlsx_to_pdf(self, xlsx_bytes):
        """Convierte bytes de un XLSX a PDF usando LibreOffice headless."""
        with tempfile.TemporaryDirectory() as tmp:
            xlsx_path = os.path.join(tmp, 'report.xlsx')
            with open(xlsx_path, 'wb') as fh:
                fh.write(xlsx_bytes)

            profile = 'file://%s' % os.path.join(tmp, 'profile')
            result = None
            for binary in ('libreoffice', 'soffice'):
                try:
                    result = subprocess.run(
                        [
                            binary,
                            '-env:UserInstallation=%s' % profile,
                            '--headless', '--convert-to',
                            'pdf:calc_pdf_Export',
                            '--outdir', tmp, xlsx_path,
                        ],
                        capture_output=True, timeout=110,
                    )
                    break
                except FileNotFoundError:
                    continue
                except subprocess.TimeoutExpired:
                    raise UserError(_(
                        'La conversion a PDF excedio el tiempo limite. '
                        'El reporte puede ser demasiado grande.'
                    ))

            if result is None:
                raise UserError(
                    _('LibreOffice no esta disponible en el servidor.')
                )

            pdf_path = os.path.join(tmp, 'report.pdf')
            if result.returncode != 0 or not os.path.exists(pdf_path):
                err = (result.stderr or b'').decode('utf-8', 'replace')[:500]
                raise UserError(
                    _('No se pudo generar el PDF.\n%s')
                    % (err or 'Error desconocido de LibreOffice.')
                )

            with open(pdf_path, 'rb') as fh:
                return fh.read()

    # ==================================================================
    # DATA - Formato 3.1 Balance General
    # ==================================================================
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
    # ------------------------------------------------------------------
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

    # Clases de resultados (gestion, naturaleza, saldos intermedios, costos).
    PL_CLASSES = ('6', '7', '8', '9')

    # Lineas de PASIVO / PATRIMONIO: su saldo natural es acreedor, por lo
    # que se muestran como (credito - debito).
    LIABILITY_KEYS = {
        'sobregiros', 'cxp_com', 'cxp_vinc', 'otras_cxp', 'parte_cte_lp',
        'deudas_lp', 'cxp_vinc_lp', 'ing_dif', 'ir_dif_pas',
        'capital', 'capital_adic', 'acciones_inv', 'exced_reval',
        'reservas_leg', 'otras_reservas', 'resultados_acum',
    }

    def _get_data_31(self):
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

    def _is_pl_code(self, code):
        """True si la cuenta es de resultados del periodo (clases 6 a 9),
        excepto la 89 (determinacion del resultado), que solo la mueven los
        asientos de cierre/apertura y va a resultados acumulados."""
        return code[:1] in self.PL_CLASSES and not code.startswith('89')

    # ==================================================================
    # Saldos por cuenta (compartido por todos los formatos)
    # ==================================================================
    def _balances_by_account(self, date_to, account_ids=None):
        """Saldo (debe - haber) por account_id de asientos posteados hasta
        `date_to` inclusive. Si se pasa `account_ids`, filtra por esas
        cuentas. Retorna {account_id: saldo}.

        En Odoo 18 `account.account.code` es company-dependent y no existe
        como columna en account_account, por eso se agrupa por account_id.
        """
        self.ensure_one()
        query = """
            SELECT aml.account_id, COALESCE(SUM(aml.debit - aml.credit), 0.0)
            FROM account_move_line aml
            JOIN account_move am ON am.id = aml.move_id
            WHERE am.company_id = %(company)s
              AND am.state = 'posted'
              AND am.date <= %(date_to)s
              AND am.id NOT IN %(excluded)s
        """
        params = {
            'company': self.company_id.id,
            'date_to': date_to,
            'excluded': self._get_excluded_move_ids(),
        }
        if account_ids is not None:
            if not account_ids:
                return {}
            query += " AND aml.account_id IN %(accounts)s"
            params['accounts'] = tuple(account_ids)
        query += " GROUP BY aml.account_id"
        self.env.cr.execute(query, params)
        return {r[0]: float(r[1] or 0.0) for r in self.env.cr.fetchall() if r[0]}

    def _get_excluded_move_ids(self):
        """Asientos de cierre del ejercicio que no se consideran en los
        saldos: los de los diarios de cierre con fecha igual a `date_end`
        (saldos antes del cierre). Tupla no vacia, apta para `NOT IN`."""
        self.ensure_one()
        ids = []
        if self.closing_journal_ids and self.date_end:
            ids = self.env['account.move'].search([
                ('company_id', '=', self.company_id.id),
                ('journal_id', 'in', self.closing_journal_ids.ids),
                ('date', '=', self.date_end),
                ('state', '=', 'posted'),
            ]).ids
        return tuple(ids) or (0,)

    def _get_period_closing_opening_move_ids(self):
        """Asientos de los diarios de cierre o apertura dentro del periodo
        [date_start, date_end]. No son movimientos, flujos ni resultados
        del periodo. Tupla no vacia, apta para `NOT IN`."""
        self.ensure_one()
        journals = self.closing_journal_ids | self.opening_journal_ids
        ids = []
        if journals and self.date_start and self.date_end:
            ids = self.env['account.move'].search([
                ('company_id', '=', self.company_id.id),
                ('journal_id', 'in', journals.ids),
                ('date', '>=', self.date_start),
                ('date', '<=', self.date_end),
                ('state', '=', 'posted'),
            ]).ids
        return tuple(ids) or (0,)

    def _account_balances_as_of(self, date_to=None):
        """Saldo por codigo de cuenta hasta `date_to` (por defecto
        `date_end`). Retorna {codigo: saldo}."""
        self.ensure_one()
        by_id = self._balances_by_account(date_to or self.date_end)
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).browse(list(by_id))
        result = {}
        for account in accounts:
            code = account.code or ''
            if code:
                result[code] = result.get(code, 0.0) + by_id[account.id]
        return result