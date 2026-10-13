# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    jeal_credit_approver_id = fields.Many2one(
        related='company_id.jeal_credit_approver_id', readonly=False)
    jeal_link_validity_hours = fields.Integer(
        related='company_id.jeal_link_validity_hours', readonly=False)
    jeal_require_approval_overdue = fields.Boolean(
        related='company_id.jeal_require_approval_overdue', readonly=False)
    jeal_debt_include_draft = fields.Boolean(
        related='company_id.jeal_debt_include_draft', readonly=False)
    jeal_debt_include_so_unbilled = fields.Boolean(
        related='company_id.jeal_debt_include_so_unbilled', readonly=False)
    jeal_debt_subtract_advances = fields.Boolean(
        related='company_id.jeal_debt_subtract_advances', readonly=False)
