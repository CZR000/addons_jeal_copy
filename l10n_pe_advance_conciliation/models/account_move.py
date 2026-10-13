# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class AccountMove(models.Model):
    _inherit = "account.move"

    advance_ids = fields.One2many(
        "l10n_pe.advance", "origin_move_id",
        string="Documentos generados", copy=False,
    )
    advance_application_ids = fields.One2many(
        "l10n_pe.advance.application", "move_id",
        string="Anticipos/revolventes aplicados", copy=False,
    )
    advance_generated_count = fields.Integer(
        compute="_compute_advance_counts", string="N. documentos generados",
    )
    advance_application_count = fields.Integer(
        compute="_compute_advance_counts", string="N. aplicaciones",
    )
    advance_applied_base = fields.Monetary(
        compute="_compute_advance_counts", currency_field="currency_id",
        string="Base aplicada por anticipos",
    )
    advance_available_amount = fields.Monetary(
        compute="_compute_advance_available", currency_field="currency_id",
        string="Anticipos disponibles",
    )
    revolving_available_amount = fields.Monetary(
        compute="_compute_advance_available", currency_field="currency_id",
        string="Revolvente disponible",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends("advance_ids", "advance_application_ids.amount_base")
    def _compute_advance_counts(self):
        for move in self:
            m = move.sudo()
            move.advance_generated_count = len(m.advance_ids)
            apps = m.advance_application_ids.filtered("active")
            move.advance_application_count = len(apps)
            move.advance_applied_base = sum(apps.mapped("amount_base"))

    def _compute_advance_available(self):
        Advance = self.env["l10n_pe.advance"].sudo()
        for move in self:
            avail_adv = 0.0
            avail_rev = 0.0
            partner = move.commercial_partner_id
            if partner and move.state == "draft" and move.move_type in (
                "out_invoice", "out_refund", "in_invoice", "in_refund"
            ):
                atype = (
                    "customer"
                    if move.move_type in ("out_invoice", "out_refund")
                    else "supplier"
                )
                advances = Advance.search([
                    ("partner_id", "=", partner.id),
                    ("advance_type", "=", atype),
                    ("state", "in", ("open", "partial")),
                    ("company_id", "=", move.company_id.id),
                ])
                avail_adv = sum(advances.mapped("amount_residual"))
            if partner and move.state == "posted" and move.move_type in (
                "out_invoice", "in_invoice"
            ):
                revolvings = Advance.search([
                    ("partner_id", "=", partner.id),
                    ("advance_type", "=", "revolving"),
                    ("state", "in", ("open", "partial")),
                    ("company_id", "=", move.company_id.id),
                ])
                avail_rev = sum(revolvings.mapped("amount_residual"))
            move.advance_available_amount = avail_adv
            move.revolving_available_amount = avail_rev

    # ------------------------------------------------------------------
    # Posting hooks
    # ------------------------------------------------------------------
    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        for move in posted:
            move._l10n_pe_generate_advance_documents()
            move._l10n_pe_reconcile_advance_lines()
        return posted

    def _l10n_pe_generate_advance_documents(self):
        """Al publicar: crea el documento de anticipo (producto de origen)
        o el revolvente (haber en la cuenta de control del revolvente)."""
        self.ensure_one()
        Advance = self.env["l10n_pe.advance"].sudo()
        Config = self.env["l10n_pe.advance.config"].sudo()

        # --- Anticipos de cliente / proveedor ---------------------------
        if self.move_type in ("out_invoice", "out_refund",
                              "in_invoice", "in_refund"):
            origin_lines = self.invoice_line_ids.filtered(
                lambda l: l.product_id.advance_role == "origin"
            )
            atype = (
                "customer"
                if self.move_type in ("out_invoice", "out_refund")
                else "supplier"
            )
            for account in origin_lines.mapped("account_id"):
                # No duplicar si ya existe el documento para este origen/cuenta.
                if self.advance_ids.filtered(
                    lambda a: a.control_account_id == account
                    and a.advance_type == atype
                ):
                    continue
                config = Config._get_config(
                    atype, control_account=account,
                    currency=self.currency_id, company=self.company_id,
                )
                control_lines = self.line_ids.filtered(
                    lambda l: l.account_id == account
                )
                base = abs(sum(control_lines.mapped("amount_currency")))
                if self.currency_id.is_zero(base):
                    continue
                Advance.create({
                    "advance_type": atype,
                    "partner_id": self.commercial_partner_id.id,
                    "currency_id": self.currency_id.id,
                    "company_id": self.company_id.id,
                    "date": self.invoice_date or self.date,
                    "config_id": config.id if config else False,
                    "control_account_id": account.id,
                    "origin_move_id": self.id,
                    "contract_ref": self.ref or self.invoice_origin or False,
                    "amount_base": base,
                    "amount_tax": abs(self.amount_tax),
                    "amount_total": abs(self.amount_total),
                })

        # --- Revolventes -------------------------------------------------
        self._l10n_pe_generate_revolving_documents()

    def _l10n_pe_generate_revolving_documents(self):
        self.ensure_one()
        Advance = self.env["l10n_pe.advance"].sudo()
        Config = self.env["l10n_pe.advance.config"].sudo()
        rev_configs = Config.search([
            ("advance_type", "=", "revolving"),
            ("company_id", "=", self.company_id.id),
        ])
        for config in rev_configs:
            # Acotacion (pendiente 10.2): solo diarios configurados disparan.
            if config.revolving_journal_ids and \
                    self.journal_id not in config.revolving_journal_ids:
                continue
            credit_lines = self.line_ids.filtered(
                lambda l: l.account_id == config.control_account_id
                and l.credit > 0
                and l.partner_id
            )
            for line in credit_lines:
                if self.advance_ids.filtered(
                    lambda a: a.advance_type == "revolving"
                    and a.partner_id == line.partner_id
                    and a.control_account_id == config.control_account_id
                ):
                    continue
                deposit = abs(
                    line.amount_currency if line.currency_id else line.balance
                )
                if config.currency_id.is_zero(deposit):
                    continue
                Advance.create({
                    "advance_type": "revolving",
                    "partner_id": line.partner_id.id,
                    "currency_id": config.currency_id.id,
                    "company_id": self.company_id.id,
                    "date": self.date,
                    "config_id": config.id,
                    "control_account_id": config.control_account_id.id,
                    "origin_move_id": self.id,
                    "amount_base": deposit,
                    "amount_total": deposit,
                })

    def _l10n_pe_reconcile_advance_lines(self):
        """Concilia cada linea negativa de anticipo con el apunte de la cuenta
        de control del anticipo origen, y registra la aplicacion."""
        self.ensure_one()
        Application = self.env["l10n_pe.advance.application"].sudo()
        app_lines = self.line_ids.filtered(
            lambda l: l.l10n_pe_advance_id
            and l.account_id.reconcile
        )
        for line in app_lines:
            advance = line.l10n_pe_advance_id.sudo()
            # Evitar registrar dos veces (p. ej. post->draft->post).
            if Application.search_count([
                ("move_line_id", "=", line.id),
                ("advance_id", "=", advance.id),
            ]):
                continue
            origin_line = advance._get_open_control_line()
            full_reconcile = False
            if origin_line and not line.reconciled:
                (line + origin_line).sudo().reconcile()
                full_reconcile = line.full_reconcile_id.id
            app_type = (
                "credit_note"
                if self.move_type in ("out_refund", "in_refund")
                else "invoice"
            )
            Application.create({
                "advance_id": advance.id,
                "move_id": self.id,
                "move_line_id": line.id,
                "date": self.invoice_date or self.date,
                "application_type": app_type,
                "amount_base": abs(line.amount_currency),
                "amount_total": abs(line.price_total),
                "amount_company_currency": abs(line.balance),
                "full_reconcile_id": full_reconcile,
            })

    # ------------------------------------------------------------------
    # Back to draft
    # ------------------------------------------------------------------
    def button_draft(self):
        for move in self:
            # Romper solo las conciliaciones de las lineas de anticipo y
            # liberar el saldo, borrando las aplicaciones asociadas.
            apps = self.env["l10n_pe.advance.application"].sudo().search([
                ("move_id", "=", move.id),
            ])
            recon_lines = apps.mapped("move_line_id").filtered("reconciled")
            recon_lines += move.line_ids.filtered(
                lambda l: l.l10n_pe_advance_id and l.reconciled
            )
            if recon_lines:
                recon_lines.sudo().remove_move_reconcile()
            apps.unlink()
        return super().button_draft()

    # ------------------------------------------------------------------
    # Actions (buttons)
    # ------------------------------------------------------------------
    def action_open_advance_apply_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aplicar anticipos"),
            "res_model": "l10n_pe.advance.apply.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
        }

    def action_open_revolving_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Aplicar revolvente"),
            "res_model": "l10n_pe.advance.revolving.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_move_id": self.id},
        }

    def action_view_generated_advances(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "res_model": "l10n_pe.advance",
            "view_mode": "list,form",
            "domain": [("id", "in", self.advance_ids.ids)],
        }
