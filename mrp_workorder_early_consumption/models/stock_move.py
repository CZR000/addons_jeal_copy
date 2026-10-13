# -*- coding: utf-8 -*-
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)


class StockMove(models.Model):
    _inherit = "stock.move"

    '''
    wo_auto_consumable = fields.Boolean(
        string="Workorder Auto Consumable",
        default=False,
        index=True,
        help="Technical flag: move generated automatically at Work Order completion.",
    )
    '''

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _woec_get_workcenter_analytic_distribution(self):
        """Devuelve el analytic_distribution (dict {ids_string: percentage})
        del workcenter asociado a la WO del move, o False si no hay.
        """
        self.ensure_one()
        wo = self.workorder_id
        if not wo or not wo.workcenter_id:
            return False
        wc = wo.workcenter_id

        if 'analytic_distribution' in wc._fields and wc.analytic_distribution:
            return dict(wc.analytic_distribution)

        for fname in (
            "costs_hour_account_id",
            "costs_hour_analytic_account_id",
            "consumption_analytic_account_id",
            "analytic_account_id",
        ):
            if fname in wc._fields and wc[fname]:
                aa = wc[fname]
                if getattr(aa, "_name", "") == "account.analytic.account":
                    return {str(aa.id): 100.0}
        return False

    def _woec_is_raw_consumption_move(self):
        self.ensure_one()
        return bool(
            self.raw_material_production_id
            and self.location_dest_id
            and self.location_dest_id.usage == "production"
        )

    # -------------------------------------------------------------------------
    # Overrides
    # -------------------------------------------------------------------------

    def _get_analytic_distribution(self):
        """Override v18 del helper unificado que devuelve el dict de
        distribución analítica del move.
        """
        if self.workorder_id and self._woec_is_raw_consumption_move():
            dist = self._woec_get_workcenter_analytic_distribution()
            if dist:
                return dist
        return super()._get_analytic_distribution()

    def _prepare_account_move_line(self, qty, cost, credit_account_id, debit_account_id, *args, **kwargs):
        """Aplica la analítica del workcenter directamente sobre las líneas
        contables (lado débito) generadas por la valoración del consumo de
        materia prima.
        """
        self.ensure_one()
        move_lines = super()._prepare_account_move_line(
            qty, cost, credit_account_id, debit_account_id, *args, **kwargs
        )

        if not (self.workorder_id and self._woec_is_raw_consumption_move()):
            return move_lines

        dist = self._woec_get_workcenter_analytic_distribution()
        if not dist:
            return move_lines

        def _iter_dicts(lines):
            for line in lines or []:
                if isinstance(line, dict):
                    yield line
                elif isinstance(line, (list, tuple)) and len(line) == 3 and isinstance(line[2], dict):
                    yield line[2]

        applied = 0
        for vals in _iter_dicts(move_lines):
            if vals.get("analytic_distribution"):
                continue

            account_id = vals.get("account_id")
            if account_id != debit_account_id:
                continue

            balance = vals.get("balance")
            if balance is None:
                debit = float(vals.get("debit") or 0.0)
                credit = float(vals.get("credit") or 0.0)
                balance = debit - credit

            if balance > 0:
                vals["analytic_distribution"] = dist
                applied += 1

        if applied:
            _logger.info(
                "[WOEC] Applied analytic_distribution %s on %s valuation line(s) for move %s (WO=%s, WC=%s)",
                dist,
                applied,
                self.id,
                self.workorder_id.id,
                self.workorder_id.workcenter_id.id if self.workorder_id.workcenter_id else None,
            )
        return move_lines

    def _ignore_automatic_valuation(self):
        self.ensure_one()
        if self.env.context.get("woec_force_valuation") and self.raw_material_production_id:
            return False
        return super()._ignore_automatic_valuation()