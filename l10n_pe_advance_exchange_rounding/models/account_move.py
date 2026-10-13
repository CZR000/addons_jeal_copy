# -*- coding: utf-8 -*-
import logging
from collections import defaultdict

from odoo import Command, _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_is_zero

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    # ------------------------------------------------------------------ #
    #  Detección del residuo de redondeo de anticipos                    #
    # ------------------------------------------------------------------ #
    def _l10n_pe_advance_rounding_term_lines(self):
        """Por cada asiento, devuelve las líneas de término de pago (por cobrar)
        que quedaron con un residuo de redondeo en moneda de la compañía tras
        aplicar un anticipo:

        - la factura es en moneda extranjera,
        - contiene al menos una línea de producto marcado como anticipo,
        - la línea por cobrar tiene importe en divisa == 0 (saldada en divisa),
        - pero su balance en moneda de compañía != 0,
        - y no está conciliada (el residuo es puro redondeo, no un cobro real).

        Devuelve: {move_id: term_lines_recordset}
        """
        result = {}
        for move in self:
            if move.state != "posted":
                continue
            company = move.company_id
            cur = move.currency_id
            comp_cur = company.currency_id
            if not cur or cur == comp_cur:
                continue
            if move.move_type not in ("out_invoice", "out_refund"):
                continue
            has_advance = any(
                line.product_id.product_tmpl_id.l10n_pe_advance
                for line in move.invoice_line_ids
                if line.product_id
            )
            if not has_advance:
                continue
            term_lines = move.line_ids.filtered(
                lambda l: l.display_type == "payment_term"
                and l.account_id.account_type
                in ("asset_receivable", "liability_payable")
                and float_is_zero(l.amount_currency, precision_rounding=cur.rounding)
                and not float_is_zero(l.balance, precision_rounding=comp_cur.rounding)
                and not l.reconciled
                and not l.matched_debit_ids
                and not l.matched_credit_ids
            )
            if term_lines:
                result[move.id] = term_lines
        return result

    # ------------------------------------------------------------------ #
    #  Reclasificación del residuo a la cuenta de diferencia de cambio   #
    # ------------------------------------------------------------------ #
    def _l10n_pe_create_rounding_adjustment(self, term_lines):
        """Crea (y publica) un asiento de ajuste que lleva el residuo de
        redondeo de la(s) línea(s) por cobrar a la cuenta de diferencia de
        cambio de la compañía, y lo concilia contra esa(s) línea(s), dejando la
        cuenta por cobrar en cero. Mismo mecanismo que usa Odoo para las
        diferencias de cambio en conciliación (asiento separado + conciliación).
        """
        self.ensure_one()
        company = self.company_id
        comp_cur = company.currency_id
        exchange_journal = company.currency_exchange_journal_id
        if not exchange_journal:
            raise UserError(
                _("La compañía %s no tiene configurado el diario de diferencia "
                  "de cambio.") % company.display_name
            )
        analytic = getattr(company, "exchange_diff_analytic_account_id", False)
        analytic_dist = {str(analytic.id): 100.0} if analytic else False

        # Agrupar por cuenta por cobrar (normalmente una sola)
        lines_by_account = defaultdict(lambda: self.env["account.move.line"])
        for line in term_lines:
            lines_by_account[line.account_id] |= line

        adj_line_commands = []
        recon_plan = []  # (ar_account, invoice_lines)
        ref = _("Redondeo dif. cambio anticipo %s") % (self.name or "")
        for ar_account, inv_lines in lines_by_account.items():
            residual = sum(inv_lines.mapped("balance"))
            if float_is_zero(residual, precision_rounding=comp_cur.rounding):
                continue
            # residuo > 0 (débito colgado en la cuenta por cobrar) => pérdida (67x)
            # residuo < 0 (crédito colgado)                        => ganancia (77x)
            if residual > 0:
                exchange_account = company.expense_currency_exchange_account_id
            else:
                exchange_account = company.income_currency_exchange_account_id
            if not exchange_account:
                raise UserError(
                    _("La compañía %s no tiene configurada la cuenta de "
                      "diferencia de cambio.") % company.display_name
                )
            cur_id = (inv_lines[0].currency_id or self.currency_id).id
            partner_id = self.commercial_partner_id.id
            # Contrapartida en la cuenta por cobrar (signo opuesto al residuo)
            adj_line_commands.append(
                Command.create({
                    "name": ref,
                    "account_id": ar_account.id,
                    "partner_id": partner_id,
                    "currency_id": cur_id,
                    "amount_currency": 0.0,
                    "debit": 0.0 if residual > 0 else -residual,
                    "credit": residual if residual > 0 else 0.0,
                })
            )
            # Línea en la cuenta de diferencia de cambio (mismo signo que el residuo)
            exch_vals = {
                "name": ref,
                "account_id": exchange_account.id,
                "partner_id": partner_id,
                "currency_id": cur_id,
                "amount_currency": 0.0,
                "debit": residual if residual > 0 else 0.0,
                "credit": 0.0 if residual > 0 else -residual,
            }
            if analytic_dist:
                exch_vals["analytic_distribution"] = analytic_dist
            adj_line_commands.append(Command.create(exch_vals))
            recon_plan.append((ar_account, inv_lines))

        if not adj_line_commands:
            return False

        adj = self.env["account.move"].with_context(
            skip_destination_move_generation=True,
            skip_advance_rounding_reclassify=True,
        ).create({
            "move_type": "entry",
            "journal_id": exchange_journal.id,
            "date": self.date,
            "ref": ref,
            "line_ids": adj_line_commands,
        })
        adj.with_context(
            skip_destination_move_generation=True,
            skip_advance_rounding_reclassify=True,
        )._post(soft=False)

        # Conciliar la línea por cobrar residual con su contrapartida del ajuste
        for ar_account, inv_lines in recon_plan:
            adj_ar = adj.line_ids.filtered(
                lambda l: l.account_id == ar_account
            )
            (inv_lines | adj_ar).reconcile()
        return adj

    def _l10n_pe_reclassify_advance_rounding(self, raise_on_error=False):
        """Reclasifica el residuo de redondeo de anticipos de los asientos
        indicados. Idempotente: los asientos ya corregidos dejan de calificar.
        Devuelve el recordset de facturas corregidas."""
        mapping = self._l10n_pe_advance_rounding_term_lines()
        if not mapping:
            return self.env["account.move"]
        fixed = self.env["account.move"]
        for move in self.browse(list(mapping.keys())):
            try:
                with self.env.cr.savepoint():
                    adj = move._l10n_pe_create_rounding_adjustment(mapping[move.id])
                if adj:
                    fixed |= move
            except Exception as exc:  # noqa: BLE001
                _logger.warning(
                    "l10n_pe_advance_exchange_rounding: no se pudo reclasificar "
                    "el redondeo del asiento %s: %s",
                    move.name, exc,
                )
                if raise_on_error:
                    raise
        if fixed:
            _logger.info(
                "l10n_pe_advance_exchange_rounding: redondeo reclasificado en "
                "%s asiento(s): %s", len(fixed), fixed.ids,
            )
        return fixed

    # ------------------------------------------------------------------ #
    #  Ganchos de ciclo de vida y acciones públicas                      #
    # ------------------------------------------------------------------ #
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        if not self.env.context.get("skip_advance_rounding_reclassify"):
            # Defensivo: nunca bloquear la publicación de la factura por esto.
            posted._l10n_pe_reclassify_advance_rounding(raise_on_error=False)
        return posted

    def action_l10n_pe_reclassify_advance_rounding(self):
        """Acción de servidor / botón: reclasifica el redondeo de los asientos
        seleccionados. Público para poder llamarse desde la UI o por RPC."""
        return self._l10n_pe_reclassify_advance_rounding(raise_on_error=True).ids

    @api.model
    def l10n_pe_fix_all_advance_rounding(self, limit=None):
        """Recorre todas las facturas de cliente publicadas con anticipo y
        reclasifica el residuo de redondeo colgado en la cuenta por cobrar.
        Devuelve la lista de ids corregidos. Idempotente."""
        advance_products = self.env["product.product"].search(
            [("product_tmpl_id.l10n_pe_advance", "=", True)]
        )
        if not advance_products:
            return []
        domain = [
            ("move_type", "in", ("out_invoice", "out_refund")),
            ("state", "=", "posted"),
            ("invoice_line_ids.product_id", "in", advance_products.ids),
        ]
        moves = self.search(domain, limit=limit)
        fixed = moves._l10n_pe_reclassify_advance_rounding(raise_on_error=False)
        return fixed.ids
