import json
import logging
import time
from collections import defaultdict
from dateutil.relativedelta import relativedelta

from odoo import models, api, fields, _, Command
from odoo.tools import format_date
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class MulticurrencyRevaluationDualRateWizard(models.TransientModel):
    _name = 'account.multicurrency.revaluation.dual.rate.wizard'
    _description = 'Multicurrency Revaluation Dual Rate Wizard'
    _inherit = "analytic.mixin"

    # Tipos de cuenta reutilizados en varios lugares
    _EXCLUDED_ACCOUNT_TYPES = (
        'income', 'income_other', 'expense', 'expense_depreciation',
        'expense_direct_cost', 'off_balance',
    )
    _ASSET_ACCOUNT_TYPES = (
        'asset_receivable', 'asset_cash', 'asset_current',
        'asset_non_current', 'asset_prepayments', 'asset_fixed',
    )
    _LIABILITY_ACCOUNT_TYPES = (
        'liability_payable', 'liability_credit_card',
        'liability_current', 'liability_non_current',
    )

    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    journal_id = fields.Many2one(
        comodel_name='account.journal',
        compute='_compute_accounting_values',
        inverse='_inverse_revaluation_journal',
        compute_sudo=True,
        domain=[('type', '=', 'general')],
        required=True,
        readonly=False,
    )
    date = fields.Date(
        default=lambda self: self._context['multicurrency_revaluation_report_options']['date']['date_to'],
        required=True,
    )
    reversal_date = fields.Date(required=True)
    expense_provision_account_id = fields.Many2one(
        comodel_name='account.account',
        compute='_compute_accounting_values',
        inverse='_inverse_expense_provision_account',
        compute_sudo=True,
        string="Expense Account",
        required=True,
        readonly=False,
    )
    analytic_distribution = fields.Json(string='Analytic Distribution')
    income_provision_account_id = fields.Many2one(
        comodel_name='account.account',
        compute='_compute_accounting_values',
        inverse='_inverse_income_provision_account',
        compute_sudo=True,
        string="Income Account",
        required=True,
        readonly=False,
    )
    preview_data = fields.Text(compute='_compute_preview_data')
    show_warning_move_id = fields.Many2one('account.move', compute='_compute_show_warning')
    fiscal_closure = fields.Boolean(
        string='Fiscal Closure',
        default=False,
    )
    entry_per_move = fields.Boolean(
        string='One Entry Per Document',
        default=False,
        help='When enabled, creates a separate adjustment entry for each source document '
             '(invoice, bill, journal entry) instead of a single consolidated entry. '
             'Each adjustment entry will be linked to its source document via a smart button.',
    )
    create_as_draft = fields.Boolean(
        string='Crear como borrador',
        default=True,
        help='When enabled (with One Entry Per Document), creates all adjustment entries '
             'in draft state without posting them. You can then review and post them in '
             'batches manually from the journal entries list. Reversal entries will be '
             'generated automatically upon posting each batch. '
             'Recommended for large volumes to avoid request timeouts.',
    )

    # -------------------------------------------------------------------------
    # Defaults & lightweight validation
    # -------------------------------------------------------------------------

    @api.model
    def default_get(self, fields_list):
        rec = super().default_get(fields_list)
        if 'reversal_date' in fields_list:
            report_options = self._context['multicurrency_revaluation_report_options']
            rec['reversal_date'] = fields.Date.to_date(report_options['date']['date_to']) + relativedelta(days=1)

        # Chequeo ligero: verificar si existe al menos un AML candidato,
        # en lugar de correr el reporte completo (que puede tomar minutos).
        if not self._context.get('revaluation_no_loop'):
            if not self._has_any_adjustment_candidate():
                raise UserError(_("No adjustment needed"))
        return rec

    def _has_any_adjustment_candidate(self):
        """Check rápido: ¿existe al menos un AML con saldo pendiente en moneda extranjera?

        Reemplaza la validación pesada que corría el reporte completo. Usa un
        SELECT ... LIMIT 1 que Postgres puede responder en milisegundos con los
        índices apropiados.
        """
        options = self._context.get('multicurrency_revaluation_report_options', {})
        date_to = fields.Date.to_date(options['date']['date_to'])
        currency_ids = [int(cid) for cid in options.get('currency_rates', {}).keys()]
        if not currency_ids:
            return False

        self.env.cr.execute("""
            SELECT 1
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             WHERE aml.company_id = %s
               AND aml.parent_state = 'posted'
               AND aml.date <= %s
               AND aml.currency_id = ANY(%s)
               AND aml.currency_id != aml.company_currency_id
               AND acc.account_type NOT IN %s
               AND acc.reconcile = TRUE
               AND aml.amount_residual_currency != 0
             LIMIT 1
        """, (
            self.env.company.id,
            date_to,
            currency_ids,
            self._EXCLUDED_ACCOUNT_TYPES,
        ))
        return bool(self.env.cr.fetchone())

    # -------------------------------------------------------------------------
    # Computes
    # -------------------------------------------------------------------------

    @api.depends('expense_provision_account_id', 'income_provision_account_id', 'reversal_date')
    def _compute_show_warning(self):
        for record in self:
            last_move = self.env['account.move.line'].search([
                ('account_id', 'in', (record.expense_provision_account_id + record.income_provision_account_id).ids),
                ('date', '<', record.reversal_date),
            ], order='date desc', limit=1).move_id
            record.show_warning_move_id = False if last_move.reversed_entry_id else last_move

    @api.depends('expense_provision_account_id', 'income_provision_account_id', 'date', 'journal_id', 'entry_per_move', 'create_as_draft')
    def _compute_preview_data(self):
        """Preview del asiento consolidado.

        En modo `entry_per_move` no se genera preview porque implicaría correr
        toda la lectura por AML y armar N asientos, lo cual es demasiado costoso
        para hacerlo en cada cambio de campo del formulario.
        """
        preview_columns = [
            {'field': 'account_id', 'label': _("Account")},
            {'field': 'name', 'label': _("Label")},
            {'field': 'debit', 'label': _("Debit"), 'class': 'text-end text-nowrap'},
            {'field': 'credit', 'label': _("Credit"), 'class': 'text-end text-nowrap'},
        ]
        for record in self:
            if record.entry_per_move:
                # Preview desactivado en modo per-move para no colgar el formulario.
                info_msg = _(
                    "Preview is not available when 'One Entry Per Document' is enabled. "
                    "One adjustment entry will be created per source document upon confirmation."
                )
                if record.create_as_draft:
                    info_msg = _(
                        "Preview is not available when 'One Entry Per Document' is enabled. "
                        "Adjustment entries will be created in DRAFT state and can be posted "
                        "in batches later from the journal entries list."
                    )
                record.preview_data = json.dumps({
                    'groups_vals': [],
                    'options': {
                        'columns': preview_columns,
                        'info': info_msg,
                    },
                })
                continue

            preview_vals = [self.env['account.move']._move_dict_to_preview_vals(
                self._get_move_vals(),
                record.company_id.currency_id,
            )]
            record.preview_data = json.dumps({
                'groups_vals': preview_vals,
                'options': {
                    'columns': preview_columns,
                },
            })

    @api.depends('company_id')
    def _compute_accounting_values(self):
        for record in self:
            record.journal_id = record.company_id.account_revaluation_journal_id
            record.expense_provision_account_id = record.company_id.account_revaluation_expense_provision_account_id
            record.income_provision_account_id = record.company_id.account_revaluation_income_provision_account_id

    def _inverse_revaluation_journal(self):
        for record in self:
            record.company_id.sudo().account_revaluation_journal_id = record.journal_id

    def _inverse_expense_provision_account(self):
        for record in self:
            record.company_id.sudo().account_revaluation_expense_provision_account_id = record.expense_provision_account_id

    def _inverse_income_provision_account(self):
        for record in self:
            record.company_id.sudo().account_revaluation_income_provision_account_id = record.income_provision_account_id

    # -------------------------------------------------------------------------
    # Helper methods (shared by both consolidated and per-move flows)
    # -------------------------------------------------------------------------

    def _get_rate_info_for_account(self, account_type, currency_data):
        """Return (selected_rate, rate_type_label) based on the account type."""
        if account_type in self._ASSET_ACCOUNT_TYPES:
            return currency_data['purchase_rate'], _("Purchase Rate")
        elif account_type in self._LIABILITY_ACCOUNT_TYPES:
            return currency_data['sale_rate'], _("Sale Rate")
        else:
            return currency_data['sale_rate'], _("Sale Rate")

    def _build_provision_lines(self, balance, account_id, currency_id, selected_rate, rate_type):
        """Build the pair of journal item dicts (provision + offset) for one adjustment."""
        currency = self.env['res.currency'].browse(currency_id)
        company_currency = self.env.company.currency_id

        provision_line = Command.create({
            'name': _(
                "Provision for %(for_cur)s (1 %(comp_cur)s = %(rate)s %(for_cur)s - %(rate_type)s)",
                for_cur=currency.display_name,
                comp_cur=company_currency.display_name,
                rate=selected_rate,
                rate_type=rate_type,
            ),
            'debit': balance if balance > 0 else 0,
            'credit': -balance if balance < 0 else 0,
            'amount_currency': 0,
            'currency_id': currency_id,
            'account_id': account_id,
        })

        if balance < 0:
            move_line_name = _("Expense Provision for %s", currency.display_name)
        else:
            move_line_name = _("Income Provision for %s", currency.display_name)
        offset_line = Command.create({
            'name': move_line_name,
            'debit': -balance if balance < 0 else 0,
            'credit': balance if balance > 0 else 0,
            'amount_currency': 0,
            'currency_id': currency_id,
            'account_id': (
                self.expense_provision_account_id.id if balance < 0
                else self.income_provision_account_id.id
            ),
            'analytic_distribution': self.analytic_distribution if self.analytic_distribution else False,
        })

        return [provision_line, offset_line]

    # -------------------------------------------------------------------------
    # Consolidated flow (original behaviour – one entry for everything)
    # -------------------------------------------------------------------------

    @api.model
    def _get_move_vals(self):
        def _get_model_id(parsed_line, selected_model):
            for dummy, parsed_res_model, parsed_res_id in parsed_line:
                if parsed_res_model == selected_model:
                    return parsed_res_id

        def _get_adjustment_balance(line):
            for column in line.get('columns'):
                if column.get('expression_label') == 'adjustment':
                    return column.get('no_format')

        report = self.env.ref('account_multicurrency_revaluation_dual_rate.multicurrency_revaluation_dual_rate_report')
        included_line_id = report.line_ids.filtered(lambda l: l.code == 'multicurrency_included').id
        generic_included_line_id = report._get_generic_line_id('account.report.line', included_line_id)
        options = {**self._context['multicurrency_revaluation_report_options'], 'unfold_all': False}
        report_lines = report._get_lines(options)
        move_lines = []

        for report_line in report._get_unfolded_lines(report_lines, generic_included_line_id):
            parsed_line_id = report._parse_line_id(report_line.get('id'))
            balance = _get_adjustment_balance(report_line)
            if (
                parsed_line_id[-1][-2] == 'account.account'
                and not self.env.company.currency_id.is_zero(balance)
            ):
                account_id = _get_model_id(parsed_line_id, 'account.account')
                currency_id = _get_model_id(parsed_line_id, 'res.currency')
                account_type = self.env['account.account'].browse(account_id).account_type

                currency_data = options['currency_rates'][str(currency_id)]
                selected_rate, rate_type = self._get_rate_info_for_account(account_type, currency_data)

                move_lines.extend(
                    self._build_provision_lines(
                        balance, account_id, currency_id, selected_rate, rate_type,
                    )
                )

        return {
            'ref': _("Foreign currencies adjustment entry as of %s", format_date(self.env, self.date)),
            'journal_id': self.journal_id.id,
            'date': self.date,
            'line_ids': move_lines,
        }

    # -------------------------------------------------------------------------
    # Per-move flow (one entry per source document)
    # -------------------------------------------------------------------------

    def _get_move_vals_per_source_move(self):
        """Return ``{source_move_id: move_vals}`` usando amount_residual directo.

        Mucho más rápido que llamar al custom engine del reporte, ya que evita
        el query con LATERAL sobre account_partial_reconcile. Válido cuando la
        fecha del ajuste es actual (no retroactiva con reconciliaciones posteriores).
        """
        t0 = time.time()

        options = self._context['multicurrency_revaluation_report_options']
        date_to = fields.Date.to_date(options['date']['date_to'])
        company = self.env.company
        company_currency = company.currency_id
        currency_rates = options['currency_rates']

        # IDs de moneda con tasa configurada
        currency_ids = [int(cid) for cid in currency_rates.keys()]

        # Buscar AML candidatas: en moneda extranjera con saldo pendiente
        # Usamos SQL crudo con solo los campos necesarios — mucho más rápido
        # que search + browse cuando hablamos de miles de AML.
        self.env.cr.execute("""
            SELECT aml.id,
                   aml.move_id,
                   aml.account_id,
                   aml.currency_id,
                   aml.amount_residual,
                   aml.amount_residual_currency,
                   acc.account_type
              FROM account_move_line aml
              JOIN account_account acc ON acc.id = aml.account_id
             WHERE aml.company_id = %s
               AND aml.parent_state = 'posted'
               AND aml.date <= %s
               AND aml.currency_id = ANY(%s)
               AND aml.currency_id != aml.company_currency_id
               AND acc.account_type NOT IN %s
               AND acc.reconcile = TRUE
               AND aml.amount_residual_currency != 0
               AND NOT EXISTS (
                    SELECT 1
                      FROM account_account_exclude_res_currency_provision ex
                     WHERE ex.account_account_id = aml.account_id
                       AND ex.res_currency_id = aml.currency_id
               )
               AND NOT EXISTS (
                    SELECT 1
                      FROM account_partial_reconcile pex
                     WHERE pex.exchange_move_id = aml.move_id
               )
        """, (
            company.id, date_to, currency_ids, self._EXCLUDED_ACCOUNT_TYPES,
        ))

        rows = self.env.cr.dictfetchall()
        _logger.info(
            "Revaluation per-move: fetched %d candidate AMLs in %.2fs",
            len(rows), time.time() - t0,
        )

        if not rows:
            return {}

        # Agrupar por move fuente y calcular ajuste
        move_groups = defaultdict(list)

        for row in rows:
            currency_data = currency_rates.get(str(row['currency_id']))
            if not currency_data:
                continue

            # Elegir tasa según tipo de cuenta
            if row['account_type'] in self._ASSET_ACCOUNT_TYPES:
                rate = currency_data['purchase_rate']
            else:  # liability / otros
                rate = currency_data['sale_rate']

            if not rate:
                continue

            # adjustment = (residual_currency / rate) - residual_company
            new_balance = row['amount_residual_currency'] / rate
            adjustment = new_balance - row['amount_residual']

            if company_currency.is_zero(adjustment):
                continue

            move_groups[row['move_id']].append({
                'balance': adjustment,
                'account_id': row['account_id'],
                'account_type': row['account_type'],
                'currency_id': row['currency_id'],
            })

        if not move_groups:
            return {}

        # Cargar nombres de moves fuente (prefetch automático)
        source_moves = self.env['account.move'].browse(move_groups.keys())
        move_name_map = {m.id: m.name for m in source_moves}

        # Armar move_vals
        result = {}
        for source_move_id, items in move_groups.items():
            move_lines = []
            for item in items:
                currency_data = currency_rates[str(item['currency_id'])]
                selected_rate, rate_type = self._get_rate_info_for_account(
                    item['account_type'], currency_data,
                )
                move_lines.extend(
                    self._build_provision_lines(
                        item['balance'], item['account_id'], item['currency_id'],
                        selected_rate, rate_type,
                    )
                )

            if move_lines:
                result[source_move_id] = {
                    'ref': _(
                        "Foreign currencies adjustment entry for %(move_name)s as of %(date)s",
                        move_name=move_name_map.get(source_move_id, ''),
                        date=format_date(self.env, self.date),
                    ),
                    'journal_id': self.journal_id.id,
                    'date': self.date,
                    'line_ids': move_lines,
                }

        _logger.info(
            "Revaluation per-move: prepared %d source-move adjustments in %.2fs",
            len(result), time.time() - t0,
        )
        return result

    # -------------------------------------------------------------------------
    # Entry creation
    # -------------------------------------------------------------------------

    def create_entries(self):
        self.ensure_one()

        if self.entry_per_move:
            return self._create_entries_per_move()

        # --- Original consolidated flow ---
        move_vals = self._get_move_vals()
        if move_vals['line_ids']:
            move = self.env['account.move'].create(move_vals)
            move.action_post()
            self._save_closing_rates(move)
            reverse_move = move._reverse_moves(default_values_list=[{
                'ref': _("Reversal of: %s", move.ref),
            }])
            reverse_move.date = self.reversal_date
            reverse_move.action_post()

            if self.fiscal_closure:
                reverse_move.button_draft()
                reverse_move.button_cancel()

            return self._open_entries_action([move.id, reverse_move.id])

        raise UserError(_("No provision needed was found."))

    def _save_closing_rates(self, move):
        """Guarda las tasas de cierre usadas en este asiento de ajuste."""
        options = self._context.get('multicurrency_revaluation_report_options', {})
        vals_list = []
        for cur_data in options.get('currency_rates', {}).values():
            sale_r = cur_data.get('sale_rate', 0)
            purchase_r = cur_data.get('purchase_rate', 0)
            if not sale_r or not purchase_r:
                continue
            vals_list.append({
                'move_id': move.id,
                'date': move.date,
                'currency_id': cur_data['currency_id'],
                'company_id': self.company_id.id,
                # Convert from "1 PEN = X USD" (options format) to "1 USD = Y PEN" (display format)
                'sale_rate': 1.0 / sale_r,
                'purchase_rate': 1.0 / purchase_r,
            })
        if vals_list:
            self.env['account.revaluation.closing.rate'].create(vals_list)

    def _create_entries_per_move(self):
        """Create one adjustment per source document.

        Two modes:
        - create_as_draft=True (default): only create in draft state, user posts later
          in batches from the journal entries list. Fast, no timeout risk.
        - create_as_draft=False: legacy behavior (create + post + reverse + post reversal
          in a single request). Only viable for small volumes (< 500 moves).
        """
        t_total = time.time()

        moves_vals = self._get_move_vals_per_source_move()
        if not moves_vals:
            raise UserError(_("No provision needed was found."))

        # Prepare batch create vals
        vals_list = []
        source_move_ids_order = []
        for source_move_id, move_vals in moves_vals.items():
            if not move_vals['line_ids']:
                continue
            vals_list.append({
                **move_vals,
                'revaluation_source_move_id': source_move_id,
            })
            source_move_ids_order.append(source_move_id)

        if not vals_list:
            raise UserError(_("No provision needed was found."))

        # --- Modo draft: solo crear, no postear ---
        if self.create_as_draft:
            t0 = time.time()
            adjustment_moves = self.env['account.move'].create(vals_list)
            _logger.info(
                "Revaluation per-move (DRAFT): created %d adjustment moves in %.2fs",
                len(adjustment_moves), time.time() - t0,
            )

            # Guardar tasas de cierre ligadas al primer move (referencia del batch)
            self._save_closing_rates(adjustment_moves[:1])

            _logger.info(
                "Revaluation per-move (DRAFT): flow completed in %.2fs — %d moves pending posting",
                time.time() - t_total, len(adjustment_moves),
            )

            return self._open_draft_adjustments_action(adjustment_moves.ids)

        # --- Modo legacy: post + reverse en un solo request ---
        t0 = time.time()
        adjustment_moves = self.env['account.move'].create(vals_list)
        _logger.info(
            "Revaluation per-move: created %d adjustment moves in %.2fs",
            len(adjustment_moves), time.time() - t0,
        )

        t0 = time.time()
        adjustment_moves.action_post()
        _logger.info(
            "Revaluation per-move: posted %d adjustment moves in %.2fs",
            len(adjustment_moves), time.time() - t0,
        )

        self._save_closing_rates(adjustment_moves[:1])

        t0 = time.time()
        reverse_default_values = [
            {
                'ref': _("Reversal of: %s", move.ref),
                'date': self.reversal_date,
                'revaluation_source_move_id': move.revaluation_source_move_id.id,
            }
            for move in adjustment_moves
        ]
        reverse_moves = adjustment_moves._reverse_moves(default_values_list=reverse_default_values)
        _logger.info(
            "Revaluation per-move: reversed %d moves in %.2fs",
            len(reverse_moves), time.time() - t0,
        )

        t0 = time.time()
        reverse_moves.action_post()
        _logger.info(
            "Revaluation per-move: posted %d reversal moves in %.2fs",
            len(reverse_moves), time.time() - t0,
        )

        if self.fiscal_closure:
            reverse_moves.button_draft()
            reverse_moves.button_cancel()

        all_move_ids = (adjustment_moves | reverse_moves).ids

        _logger.info(
            "Revaluation per-move: full flow completed in %.2fs (%d adjustments + %d reversals)",
            time.time() - t_total, len(adjustment_moves), len(reverse_moves),
        )

        return self._open_entries_action(all_move_ids)

    def _open_entries_action(self, move_ids):
        """Return the window action to display the created entries."""
        list_view = self.env.ref('account.view_move_tree', False)
        form_view = self.env.ref('account.view_move_form', False)
        ctx = self.env.context.copy()
        ctx.pop('id', '')
        return {
            'name': _("Adjustment Entries"),
            'type': 'ir.actions.act_window',
            'res_model': "account.move",
            'domain': [('id', 'in', move_ids)],
            'view_mode': "list,form",
            'views': [
                (list_view and list_view.id or False, 'list'),
                (form_view and form_view.id or False, 'form'),
            ],
            'context': ctx,
        }

    def _open_draft_adjustments_action(self, move_ids):
        """Return action to display the DRAFT adjustment entries ready for posting.

        The reversal_date and fiscal_closure are passed via context so the
        batch-post action (defined on account.move) can retrieve them when
        the user posts a selection.
        """
        list_view = self.env.ref('account.view_move_tree', False)
        form_view = self.env.ref('account.view_move_form', False)
        return {
            'name': _("Adjustment Entries (Draft) — %d entries pending posting", len(move_ids)),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'domain': [('id', 'in', move_ids)],
            'view_mode': 'list,form',
            'views': [
                (list_view and list_view.id or False, 'list'),
                (form_view and form_view.id or False, 'form'),
            ],
            'context': {
                **self.env.context,
                'default_reversal_date': self.reversal_date.isoformat() if self.reversal_date else False,
                'default_fiscal_closure': self.fiscal_closure,
                'search_default_state': 'draft',
            },
        }