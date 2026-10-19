from odoo import models, fields, api, _
from odoo.tools import float_is_zero, SQL
from odoo.exceptions import UserError

from itertools import chain


class MulticurrencyRevaluationDualRateReport(models.AbstractModel):
    _name = 'account.multicurrency.revaluation.dual.rate.report'
    _inherit = 'account.report.custom.handler'
    _description = 'Multicurrency Revaluation Dual Rate Report'

    def _get_custom_display_config(self):
        return {
            'components': {
                'AccountReportFilters': 'account_multicurrency_revaluation_dual_rate.MulticurrencyRevaluationDualRateReportFilters',
            },
            'templates': {
                'AccountReportLineName': 'account_multicurrency_revaluation_dual_rate.MulticurrencyRevaluationDualRateReportLineName',
            },
        }

    def _custom_options_initializer(self, report, options, previous_options=None):
        super()._custom_options_initializer(report, options, previous_options=previous_options)
        active_currencies = self.env['res.currency'].search([('active', '=', True)])
        if len(active_currencies) < 2:
            raise UserError(_("You need to activate more than one currency to access this report."))

        date_to = options.get('date', {}).get('date_to')
        company_currency = self.env.company.currency_id

        rates_sale = active_currencies._get_rates(self.env.company, date_to)
        rates_purchase = active_currencies._get_purchase_rates(self.env.company, date_to)

        company_sale_rate = rates_sale[company_currency.id]
        company_purchase_rate = rates_purchase[company_currency.id]
        if float_is_zero(company_sale_rate, 20) or float_is_zero(company_purchase_rate, 20):
            raise UserError(_("Company currency rate cannot be zero."))

        new_currency_rates = {}
        for cur in active_currencies:
            sale_rate = purchase_rate = 0.0
            if not float_is_zero(rates_sale[cur.id], 20):
                sale_rate = rates_sale[cur.id] / company_sale_rate
            if not float_is_zero(rates_purchase[cur.id], 20):
                purchase_rate = rates_purchase[cur.id] / company_purchase_rate

            prev = (previous_options or {}).get('currency_rates', {}).get(str(cur.id), {})
            sale_rate = float(prev.get('sale_rate', sale_rate))
            purchase_rate = float(prev.get('purchase_rate', purchase_rate))

            if float_is_zero(sale_rate, 20) or float_is_zero(purchase_rate, 20):
                raise UserError(_("The currency rate cannot be zero."))

            new_currency_rates[str(cur.id)] = {
                'currency_id': cur.id,
                'currency_name': cur.name,
                'currency_main': company_currency.name,
                'sale_rate': sale_rate,
                'purchase_rate': purchase_rate,
            }

        options['company_currency'] = new_currency_rates.pop(str(company_currency.id))
        options['currency_rates'] = new_currency_rates

        any_custom_rate = False
        for cur_id, cr in new_currency_rates.items():
            real_sale = rates_sale[int(cur_id)] / company_sale_rate
            real_purchase = rates_purchase[int(cur_id)] / company_purchase_rate
            if (not float_is_zero(cr['sale_rate'] - real_sale, 20)
            or not float_is_zero(cr['purchase_rate'] - real_purchase, 20)):
                any_custom_rate = True
                break

        options['custom_rate'] = any_custom_rate
        options['multi_currency'] = True

        if 'buttons' not in options:
            options['buttons'] = []

        options['buttons'] = [
            button for button in options['buttons']
            if button.get('action') != 'action_multi_currency_revaluation_open_revaluation_wizard'
        ]

        options['buttons'].append({
            'name': _('Adjustment Entry'),
            'sequence': 30,
            'action': 'action_multi_currency_revaluation_dual_rate_open_revaluation_dual_rate_wizard',
            'always_show': True
        })

    def _customize_warnings(self, report, options, all_column_groups_expression_totals, warnings):
        if len(self.env.companies) > 1:
            warnings['account_multicurrency_revaluation_dual_rate.multi_currency_revaluation_dual_rate_report_warning_multicompany'] = {'alert_type': 'warning'}
        if options['custom_rate']:
            warnings['account_multicurrency_revaluation_dual_rate.multi_currency_revaluation_dual_rate_report_warning_custom_rate'] = {'alert_type': 'warning'}

    def _custom_line_postprocessor(self, report, options, lines):
        line_to_adjust_id = self.env.ref('account_multicurrency_revaluation_dual_rate.multicurrency_revaluation_dual_rate_to_adjust').id
        line_excluded_id = self.env.ref('account_multicurrency_revaluation_dual_rate.multicurrency_revaluation_dual_rate_excluded').id

        rslt = []
        for index, line in enumerate(lines):
            res_model_name, res_id = report._get_model_info_from_id(line['id'])

            is_last_line = index == len(lines) - 1
            if res_model_name == 'account.report.line' and (
                   (res_id == line_to_adjust_id and (
                       is_last_line
                       or report._get_model_info_from_id(lines[index + 1]['id']) == ('account.report.line', line_excluded_id)
                   )) or
                   (res_id == line_excluded_id and is_last_line)
            ):
                # 'To Adjust' and 'Excluded' lines need to be hidden if they have no child
                continue

            elif res_model_name == 'res.currency':
                currency_data = options['currency_rates'].get(str(res_id))
                if currency_data:
                    comp_cur = self.env.company.currency_id.display_name
                    line['name'] = _(
                        "%(cur_name)s (Sale Rate: 1 %(c_main)s = %(sr).6f %(cur_name)s, "
                        "Purchase Rate: 1 %(c_main)s = %(pr).6f %(cur_name)s)",
                        cur_name=line['name'],
                        c_main=comp_cur,
                        sr=currency_data['sale_rate'],
                        pr=currency_data['purchase_rate'],
                    )

            elif res_model_name == 'account.account':
                # Mark the included/excluded lines, so that the custom component templates knows what label to put on them
                # The parent report line (to adjust / excluded) is part of the generic line id
                line['is_included_line'] = report._get_res_id_from_line_id(line['id'], 'account.report.line') == line_to_adjust_id

            # Inject the related model into the line dict in order to use it on the custom component template on js side to display buttons
            line['cur_revaluation_line_model'] = res_model_name

            rslt.append(line)

        return rslt

    def _custom_groupby_line_completer(self, report, options, line_dict):
        model_info_from_id = report._get_model_info_from_id(line_dict['id'])
        if model_info_from_id[0] == 'res.currency':
            line_dict['unfolded'] = True
            line_dict['unfoldable'] = False

    def action_multi_currency_revaluation_dual_rate_open_revaluation_dual_rate_wizard(self, options):
        """Open the revaluation wizard."""
        form = self.env.ref('account_multicurrency_revaluation_dual_rate.view_account_multicurrency_revaluation_dual_rate_wizard', False)
        return {
            'name': _("Make Adjustment Entry"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.multicurrency.revaluation.dual.rate.wizard',
            'view_mode': 'form',
            'view_id': form.id,
            'views': [(form.id, 'form')],
            'multi': 'True',
            'target': 'new',
            'context': {
                **self._context,
                'multicurrency_revaluation_report_options': options,
            },
        }

    # ACTIONS
    def action_multi_currency_revaluation_dual_rate_open_general_ledger(self, options, params):
        report = self.env['account.report'].browse(options['report_id'])
        account_id = report._get_res_id_from_line_id(params['line_id'], 'account.account')
        account_line_id = report._get_generic_line_id('account.account', account_id)
        general_ledger_options = self.env.ref('account_reports.general_ledger_report').get_options(options)
        general_ledger_options['unfolded_lines'] = [account_line_id]

        general_ledger_action = self.env['ir.actions.actions']._for_xml_id('account_reports.action_account_report_general_ledger')
        general_ledger_action['params'] = {
            'options': general_ledger_options,
            'ignore_session': True,
        }

        return general_ledger_action

    def action_multi_currency_revaluation_dual_rate_toggle_provision(self, options, params):
        """ Include/exclude an account from the provision. """
        res_ids_map = self.env['account.report']._get_res_ids_from_line_id(params['line_id'], ['res.currency', 'account.account'])
        account = self.env['account.account'].browse(res_ids_map['account.account'])
        currency = self.env['res.currency'].browse(res_ids_map['res.currency'])
        if currency in account.exclude_provision_currency_ids:
            account.exclude_provision_currency_ids -= currency
        else:
            account.exclude_provision_currency_ids += currency
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_multi_currency_revaluation_dual_rate_open_currency_rates(self, options, params=None):
        """ Open the currency rate list. """
        currency_id = self.env['account.report']._get_res_id_from_line_id(params['line_id'], 'res.currency')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Currency Rates (%s)', self.env['res.currency'].browse(currency_id).display_name),
            'views': [(False, 'list')],
            'res_model': 'res.currency.rate',
            'context': {**self.env.context, **{'default_currency_id': currency_id, 'active_id': currency_id}},
            'domain': [('currency_id', '=', currency_id)],
        }

    def _report_custom_engine_multi_currency_revaluation_dual_rate_to_adjust(self, expressions, options, date_scope, current_groupby, next_groupby, offset=0, limit=None, warnings=None):
        return self._multi_currency_revaluation_dual_rate_get_custom_lines(options, 'to_adjust', current_groupby, next_groupby, offset=offset, limit=limit)

    def _report_custom_engine_multi_currency_revaluation_dual_rate_excluded(self, expressions, options, date_scope, current_groupby, next_groupby, offset=0, limit=None, warnings=None):
        return self._multi_currency_revaluation_dual_rate_get_custom_lines(options, 'excluded', current_groupby, next_groupby, offset=offset, limit=limit)

    def _multi_currency_revaluation_dual_rate_get_custom_lines(self, options, line_code, current_groupby, next_groupby, offset=0, limit=None):
        def build_result_dict(report, query_res):
            return {
                'balance_currency': query_res['balance_currency'] if len(query_res['currency_id']) == 1 else None,
                'currency_id': query_res['currency_id'][0] if len(query_res['currency_id']) == 1 else None,
                'balance_operation': query_res['balance_operation'],
                'balance_current': query_res['balance_current'],
                'adjustment': query_res['adjustment'],
                'has_sublines': query_res['aml_count'] > 0,
            }

        report = self.env['account.report'].browse(options['report_id'])
        report._check_groupby_fields((next_groupby.split(',') if next_groupby else []) + ([current_groupby] if current_groupby else []))

        # No need to run any SQL if we're computing the main line: it does not display any total
        if not current_groupby:
            return {
                'balance_currency': None,
                'currency_id': None,
                'balance_operation': None,
                'balance_current': None,
                'adjustment': None,
                'has_sublines': False,
            }

        query = "(VALUES {})".format(', '.join("(%s, %s, %s)" for _ in options['currency_rates']))
        params = list(chain.from_iterable(
            (cur['currency_id'], cur['sale_rate'], cur['purchase_rate'])
            for cur in options['currency_rates'].values()
        ))
        custom_currency_table_dual_rate_query = SQL(query, *params)
        date_to = options['date']['date_to']
        select_part_not_an_exchange_move_id = SQL(
            """
            NOT EXISTS (
                SELECT 1
                  FROM account_partial_reconcile part_exch
                 WHERE part_exch.exchange_move_id = account_move_line.move_id
                   AND part_exch.max_date <= %s
            )
            """,
            date_to
        )

        query = report._get_report_query(options, 'strict_range')
        groupby_field_sql = self.env['account.move.line']._field_to_sql("account_move_line", current_groupby, query)
        tail_query = report._get_engine_query_tail(offset, limit)

        case_for_rate = SQL("""CASE
            WHEN account.account_type IN ('asset_receivable', 'asset_cash', 'asset_current', 'asset_non_current', 'asset_prepayments', 'asset_fixed')
                THEN custom_currency_table_dual_rate.purchase_rate
            WHEN account.account_type IN ('liability_payable', 'liability_credit_card', 'liability_current', 'liability_non_current')
                THEN custom_currency_table_dual_rate.sale_rate
            ELSE custom_currency_table_dual_rate.sale_rate
            END
        """)

        full_query = SQL(
            """
            WITH custom_currency_table_dual_rate(currency_id, sale_rate, purchase_rate) AS (%(custom_currency_table_dual_rate_query)s)
            SELECT
                   subquery.grouping_key,
                   ARRAY_AGG(DISTINCT(subquery.currency_id)) AS currency_id,
                   SUM(subquery.balance_currency) AS balance_currency,
                   SUM(subquery.balance_operation) AS balance_operation,
                   SUM(subquery.balance_current) AS balance_current,
                   SUM(subquery.adjustment) AS adjustment,
                   COUNT(subquery.aml_id) AS aml_count
              FROM (
                -- Moves that have at least one partial at a certain date and are not fully paid at that date
                SELECT
                       grouping_key,
                       balance_operation,
                       balance_currency,
                       balance_currency / rate_to_apply AS balance_current,
                       (balance_currency / rate_to_apply) - balance_operation AS adjustment,
                       currency_id,
                       aml_id
                  FROM (
                    SELECT
                           %(groupby_field_sql)s AS grouping_key,
                           ROUND(account_move_line.balance - SUM(ara.amount_debit) + SUM(ara.amount_credit), aml_comp_currency.decimal_places) AS balance_operation,
                           ROUND(account_move_line.amount_currency - SUM(ara.amount_debit_currency) + SUM(ara.amount_credit_currency), aml_currency.decimal_places) AS balance_currency,
                           %(case_for_rate)s AS rate_to_apply,
                           account_move_line.currency_id AS currency_id,
                           account_move_line.id AS aml_id
                      FROM %(table_references)s
                      JOIN account_account account
                        ON account_move_line.account_id = account.id
                      JOIN res_currency aml_currency
                        ON account_move_line.currency_id = aml_currency.id
                      JOIN res_currency aml_comp_currency
                        ON account_move_line.company_currency_id = aml_comp_currency.id
                      JOIN custom_currency_table_dual_rate
                        ON account_move_line.currency_id = custom_currency_table_dual_rate.currency_id,
                           LATERAL (
                                   SELECT COALESCE(SUM(part.amount), 0.0) AS amount_debit,
                                          ROUND(SUM(part.debit_amount_currency), curr.decimal_places) AS amount_debit_currency,
                                          0.0 AS amount_credit,
                                          0.0 AS amount_credit_currency
                                     FROM account_partial_reconcile part
                                     JOIN res_currency curr ON curr.id = part.debit_currency_id
                                    WHERE part.debit_move_id = account_move_line.id
                                      AND part.max_date <= %(date_to)s
                                 GROUP BY curr.decimal_places
                                UNION ALL
                                   SELECT 0.0 AS amount_debit,
                                          0.0 AS amount_debit_currency,
                                          COALESCE(SUM(part.amount), 0.0) AS amount_credit,
                                          ROUND(SUM(part.credit_amount_currency), curr.decimal_places) AS amount_credit_currency
                                     FROM account_partial_reconcile part
                                     JOIN res_currency curr ON curr.id = part.credit_currency_id
                                    WHERE part.credit_move_id = account_move_line.id
                                      AND part.max_date <= %(date_to)s
                                 GROUP BY curr.decimal_places
                           ) AS ara
                     WHERE %(search_condition)s
                       AND account.account_type NOT IN ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost', 'off_balance')
                       AND (
                            account.currency_id != account_move_line.company_currency_id
                            OR (
                                account.account_type IN ('asset_receivable', 'liability_payable')
                                AND account_move_line.currency_id != account_move_line.company_currency_id
                            )
                       )
                       AND %(exist_condition)s (
                            SELECT 1
                              FROM account_account_exclude_res_currency_provision
                             WHERE account_account_id = account_move_line.account_id
                               AND res_currency_id = account_move_line.currency_id
                       )
                       AND NOT EXISTS (
                            SELECT 1
                              FROM account_partial_reconcile part_exch
                             WHERE part_exch.exchange_move_id = account_move_line.move_id
                               AND part_exch.max_date <= %(date_to)s
                       )
                  GROUP BY account_move_line.id,
                           grouping_key,
                           aml_comp_currency.decimal_places,
                           aml_currency.decimal_places,
                           account_move_line.balance,
                           account_move_line.amount_currency,
                           account_move_line.currency_id,
                           account.account_type,
                           custom_currency_table_dual_rate.sale_rate,
                           custom_currency_table_dual_rate.purchase_rate
                    HAVING ROUND(account_move_line.balance - SUM(ara.amount_debit) + SUM(ara.amount_credit), aml_comp_currency.decimal_places) != 0
                        OR ROUND(account_move_line.amount_currency - SUM(ara.amount_debit_currency) + SUM(ara.amount_credit_currency), aml_currency.decimal_places) != 0.0
                  ) partials_calc
        
                UNION ALL
        
                -- Moves that don't have a payment yet at a certain date
                SELECT
                       %(groupby_field_sql)s AS grouping_key,
                       account_move_line.balance AS balance_operation,
                       account_move_line.amount_currency AS balance_currency,
                       account_move_line.amount_currency / %(case_for_rate)s AS balance_current,
                       account_move_line.amount_currency / %(case_for_rate)s - account_move_line.balance AS adjustment,
                       account_move_line.currency_id AS currency_id,
                       account_move_line.id AS aml_id
                  FROM %(table_references)s
                  JOIN account_account account
                    ON account_move_line.account_id = account.id
                  JOIN custom_currency_table_dual_rate
                    ON custom_currency_table_dual_rate.currency_id = account_move_line.currency_id
                 WHERE %(search_condition)s
                   AND account.account_type NOT IN ('income', 'income_other', 'expense', 'expense_depreciation', 'expense_direct_cost', 'off_balance')
                   AND (
                        account.currency_id != account_move_line.company_currency_id
                        OR (
                            account.account_type IN ('asset_receivable', 'liability_payable')
                            AND account_move_line.currency_id != account_move_line.company_currency_id
                        )
                   )
                   AND %(exist_condition)s (
                        SELECT 1
                          FROM account_account_exclude_res_currency_provision
                         WHERE account_account_id = account_move_line.account_id
                           AND res_currency_id = account_move_line.currency_id
                   )
                   AND NOT EXISTS (
                        SELECT 1
                          FROM account_partial_reconcile part_exch
                         WHERE part_exch.exchange_move_id = account_move_line.move_id
                           AND part_exch.max_date <= %(date_to)s
                   )
                   AND NOT EXISTS (
                        SELECT 1 FROM account_partial_reconcile p
                        WHERE p.debit_move_id = account_move_line.id
                          AND p.max_date <= %(date_to)s
                   )
                   AND NOT EXISTS (
                        SELECT 1 FROM account_partial_reconcile p
                        WHERE p.credit_move_id = account_move_line.id
                          AND p.max_date <= %(date_to)s
                   )
                   AND (account_move_line.balance != 0.0 OR account_move_line.amount_currency != 0.0)
        
            ) subquery
        
            GROUP BY grouping_key
            ORDER BY grouping_key
            %(tail_query)s
            """,
            groupby_field_sql=groupby_field_sql,
            custom_currency_table_dual_rate_query=custom_currency_table_dual_rate_query,
            case_for_rate=case_for_rate,
            exist_condition=SQL('NOT EXISTS') if line_code == 'to_adjust' else SQL('EXISTS'),
            table_references=query.from_clause,
            date_to=date_to,
            tail_query=tail_query,
            search_condition=query.where_clause,
        )
        self._cr.execute(full_query)
        query_res_lines = self._cr.dictfetchall()

        if not current_groupby:
            return build_result_dict(report, query_res_lines and query_res_lines[0] or {})
        else:
            rslt = []
            for query_res in query_res_lines:
                grouping_key = query_res['grouping_key']
                rslt.append((grouping_key, build_result_dict(report, query_res)))
            return rslt
