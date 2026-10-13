# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class CreditApprovalSendWizard(models.TransientModel):
    _name = 'jeal.credit.approval.send.wizard'
    _description = "Enviar solicitud de aprobación de crédito"

    order_id = fields.Many2one('sale.order', string="Cotización", required=True)
    partner_id = fields.Many2one(related='order_id.partner_id')
    currency_id = fields.Many2one(related='order_id.jeal_company_currency_id')
    credit_limit = fields.Monetary(related='order_id.jeal_credit_limit')
    debt_total = fields.Monetary(related='order_id.jeal_debt_total')
    debt_overdue = fields.Monetary(related='order_id.jeal_debt_overdue')
    amount_pen = fields.Monetary(related='order_id.jeal_amount_pen')
    excess = fields.Monetary(related='order_id.jeal_excess')
    projected = fields.Monetary(
        string="Deuda con esta venta", compute='_compute_projected')
    approver_name = fields.Char(compute='_compute_approver')
    validity_hours = fields.Integer(compute='_compute_approver')

    @api.depends('debt_total', 'amount_pen')
    def _compute_projected(self):
        for wiz in self:
            wiz.projected = wiz.debt_total + wiz.amount_pen

    def _compute_approver(self):
        company = self.env.company
        for wiz in self:
            wiz.approver_name = company.jeal_credit_approver_id.name or _("(sin configurar)")
            wiz.validity_hours = company.jeal_link_validity_hours or 72

    def action_send(self):
        self.ensure_one()
        self.order_id._jeal_create_and_send_request()
        return {'type': 'ir.actions.act_window_close'}
