# -*- coding: utf-8 -*-
from odoo import _, api, fields, models


class AccountMoveLine(models.Model):
    _inherit = "account.move.line"

    analytic_account_id = fields.Many2one(
        comodel_name="account.analytic.account",
        string="Cuenta Analítica",
        compute="_compute_analytic_account_id",
        store=True,
        index=True,
        groups="analytic.group_analytic_accounting",
    )

    destination_account_id = fields.Many2one(
        comodel_name="account.account",
        string="Cuenta Destino",
        compute="_compute_destination_account_ids",
        store=True,
        index=True,
    )

    destination_account_ids = fields.Many2many(
        comodel_name="account.account",
        string="Cuentas Destino",
        compute="_compute_destination_account_ids",
        store=False,
    )

    @api.depends("analytic_distribution")
    def _compute_analytic_account_id(self):
        for line in self:
            if not line.analytic_distribution:
                line.analytic_account_id = False
                continue

            # Tomamos la clave con mayor porcentaje de forma más directa y rápida
            best_key = max(
                line.analytic_distribution, key=line.analytic_distribution.get
            )

            try:
                line.analytic_account_id = int(best_key.split(",")[0])
            except (ValueError, TypeError, IndexError):
                line.analytic_account_id = False

    @api.depends(
        "account_id.has_destination_account", "analytic_distribution", "company_id"
    )
    def _compute_destination_account_ids(self):
        for line in self:
            # 1. Condición de salida temprana (Asignamos False/Recordset vacío)
            if (
                not line.account_id.has_destination_account
                or not line.analytic_distribution
            ):
                line.destination_account_id = False
                line.destination_account_ids = False
                continue

            # 2. Extracción limpia de los IDs analíticos
            analytic_ids = []
            for key in line.analytic_distribution.keys():
                analytic_ids.extend([int(k) for k in key.split(",") if k.isdigit()])

            if not analytic_ids:
                line.destination_account_id = False
                line.destination_account_ids = False
                continue

            # 3. Evaluamos con la empresa correcta
            analytic_accounts = (
                self.env["account.analytic.account"].with_company(line.company_id)
                .browse(analytic_ids)
            )

            dest_accounts = self.env["account.account"].browse()
            for analytic in analytic_accounts.filtered("has_destination_account"):
                if analytic.destination_account_id:
                    dest_accounts |= analytic.destination_account_id

            # 4. Asignación final
            if dest_accounts:
                line.destination_account_id = dest_accounts[0]
                line.destination_account_ids = dest_accounts
            else:
                line.destination_account_id = False
                line.destination_account_ids = False
