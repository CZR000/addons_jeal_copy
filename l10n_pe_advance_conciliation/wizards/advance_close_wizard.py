# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class L10nPeAdvanceCloseWizard(models.TransientModel):
    _name = "l10n_pe.advance.close.wizard"
    _description = "Cerrar saldo residual"

    advance_id = fields.Many2one(
        "l10n_pe.advance", string="Documento", required=True,
    )
    partner_id = fields.Many2one(
        related="advance_id.partner_id", string="Socio",
    )
    currency_id = fields.Many2one(
        related="advance_id.currency_id", string="Moneda",
    )
    company_id = fields.Many2one(
        related="advance_id.company_id", string="Compania",
    )
    residual = fields.Monetary(
        related="advance_id.amount_residual", string="Saldo residual",
        currency_field="currency_id",
    )
    tolerance = fields.Float(
        related="advance_id.config_id.closing_tolerance", string="Tolerancia",
    )
    account_id = fields.Many2one(
        "account.account", string="Cuenta", compute="_compute_account",
    )
    date = fields.Date(
        string="Fecha", required=True, default=fields.Date.context_today,
    )
    journal_id = fields.Many2one(
        related="advance_id.config_id.compensation_journal_id", string="Diario",
    )

    @api.depends("advance_id", "residual")
    def _compute_account(self):
        for wiz in self:
            config = wiz.advance_id.config_id
            if not config:
                wiz.account_id = False
                continue
            # Segun el signo del saldo elige gasto o ingreso por redondeo.
            if wiz.residual >= 0:
                wiz.account_id = config.rounding_expense_account_id
            else:
                wiz.account_id = config.rounding_income_account_id

    def action_close(self):
        self.ensure_one()
        advance = self.advance_id
        company = advance.company_id
        config = advance.config_id
        if not config:
            raise UserError(_("El documento no tiene configuracion asociada."))
        if not self.account_id:
            raise UserError(
                _("Configura la cuenta de redondeo (gasto/ingreso).")
            )
        if abs(self.residual) > config.closing_tolerance:
            raise UserError(
                _("El saldo supera la tolerancia configurada.")
            )
        if advance.currency_id.is_zero(self.residual):
            raise UserError(_("El documento no tiene saldo por cerrar."))

        residual = self.residual
        balance = advance.currency_id._convert(
            residual, company.currency_id, company, self.date,
        )
        control_vals = {
            "name": _("Cierre por redondeo %s") % advance.name,
            "account_id": advance.control_account_id.id,
            "partner_id": advance.partner_id.id,
            "currency_id": advance.currency_id.id,
            "amount_currency": residual,
            "debit": balance if balance > 0 else 0.0,
            "credit": -balance if balance < 0 else 0.0,
            "l10n_pe_advance_id": advance.id,
        }
        rounding_vals = {
            "name": _("Cierre por redondeo %s") % advance.name,
            "account_id": self.account_id.id,
            "partner_id": advance.partner_id.id,
            "currency_id": advance.currency_id.id,
            "amount_currency": -residual,
            "debit": -balance if balance < 0 else 0.0,
            "credit": balance if balance > 0 else 0.0,
        }
        close_move = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.journal_id.id or config.compensation_journal_id.id,
            "date": self.date,
            "ref": _("Cierre por redondeo %s") % advance.name,
            "line_ids": [(0, 0, control_vals), (0, 0, rounding_vals)],
        })
        close_move.action_post()

        control_line = close_move.line_ids.filtered(
            lambda l: l.account_id == advance.control_account_id
        )[:1]
        origin_line = advance._get_open_control_line()
        full_reconcile = False
        if control_line and origin_line and not control_line.reconciled:
            (control_line + origin_line).sudo().reconcile()
            full_reconcile = control_line.full_reconcile_id.id

        self.env["l10n_pe.advance.application"].sudo().create({
            "advance_id": advance.id,
            "move_id": close_move.id,
            "move_line_id": control_line.id if control_line else False,
            "date": self.date,
            "application_type": "rounding",
            "amount_base": residual,
            "amount_total": residual,
            "amount_company_currency": abs(balance),
            "full_reconcile_id": full_reconcile,
        })
        return {"type": "ir.actions.act_window_close"}
