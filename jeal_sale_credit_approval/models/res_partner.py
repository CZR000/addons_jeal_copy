# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class ResPartner(models.Model):
    _inherit = 'res.partner'

    jeal_company_currency_id = fields.Many2one(
        'res.currency', compute='_compute_company_currency',
        string="Moneda de la compañía")
    jeal_credit_limit = fields.Monetary(
        string="Límite de crédito",
        currency_field='jeal_company_currency_id',
        tracking=True,
        help="Línea de crédito del cliente en soles. 0 = sin línea: toda "
             "venta al crédito requiere aprobación.",
    )
    jeal_debt_total = fields.Monetary(
        string="Deuda total", compute='_compute_credit_data',
        currency_field='jeal_company_currency_id')
    jeal_debt_overdue = fields.Monetary(
        string="Deuda vencida", compute='_compute_credit_data',
        currency_field='jeal_company_currency_id')
    jeal_credit_available = fields.Monetary(
        string="Línea disponible", compute='_compute_credit_data',
        currency_field='jeal_company_currency_id')
    jeal_credit_usage = fields.Float(
        string="% de uso", compute='_compute_credit_data')
    jeal_limit_history_ids = fields.One2many(
        'jeal.credit.limit.history', 'partner_id', string="Historial de límite")
    is_jeal_credit_manager = fields.Boolean(
        string="Puede gestionar crédito", compute='_compute_is_credit_manager')

    def _compute_is_credit_manager(self):
        admin = self.env.ref(
            'jeal_sale_credit_approval.group_jeal_credit_admin',
            raise_if_not_found=False)
        is_admin = bool(admin) and admin in self.env.user.groups_id
        is_approver = self.env.user == self.env.company.jeal_credit_approver_id
        can = is_admin or is_approver
        for partner in self:
            partner.is_jeal_credit_manager = can

    def _compute_company_currency(self):
        company = self.env.company
        for partner in self:
            partner.jeal_company_currency_id = \
                (partner.company_id or company).currency_id

    def _jeal_get_debt_components(self):
        """Devuelve la composición de la deuda total del cliente, en moneda de
        la compañía (soles). Las piezas incluidas dependen de la configuración.
        """
        self.ensure_one()
        today = fields.Date.context_today(self)
        company = self.company_id or self.env.company
        currency = company.currency_id

        # 1) Facturas pendientes de cobro + anticipos (líneas por cobrar)
        lines = self.env['account.move.line'].search([
            ('partner_id', '=', self.id),
            ('account_id.account_type', '=', 'asset_receivable'),
            ('parent_state', '=', 'posted'),
            ('reconciled', '=', False),
        ])
        pending = sum(l.amount_residual for l in lines if l.amount_residual > 0)
        advances = -sum(l.amount_residual for l in lines if l.amount_residual < 0)
        overdue = sum(
            l.amount_residual for l in lines
            if l.amount_residual > 0 and l.date_maturity and l.date_maturity < today
        )

        # 2) Facturas en borrador
        draft = 0.0
        if company.jeal_debt_include_draft:
            draft_invoices = self.env['account.move'].search([
                ('partner_id', '=', self.id),
                ('move_type', '=', 'out_invoice'),
                ('state', '=', 'draft'),
            ])
            for inv in draft_invoices:
                draft += inv.currency_id._convert(
                    inv.amount_total, currency, company,
                    inv.invoice_date or today)

        # 3) Pedidos confirmados sin facturar (importe pendiente de facturar)
        so_unbilled = 0.0
        if company.jeal_debt_include_so_unbilled:
            orders = self.env['sale.order'].search([
                ('partner_id', '=', self.id),
                ('state', '=', 'sale'),
                ('invoice_status', '!=', 'invoiced'),
            ])
            for order in orders:
                remaining = order.amount_total - order.amount_invoiced
                if remaining > 0:
                    so_unbilled += order.currency_id._convert(
                        remaining, currency, company, today)

        if not company.jeal_debt_subtract_advances:
            advances = 0.0

        total = pending + draft + so_unbilled - advances
        return {
            'pending': pending,
            'draft': draft,
            'so_unbilled': so_unbilled,
            'advances': advances,
            'overdue': overdue,
            'total': total,
        }

    @api.depends_context('company')
    def _compute_credit_data(self):
        for partner in self:
            data = partner._jeal_get_debt_components()
            total = data['total']
            limit = partner.jeal_credit_limit
            partner.jeal_debt_total = total
            partner.jeal_debt_overdue = data['overdue']
            partner.jeal_credit_available = limit - total
            partner.jeal_credit_usage = (total / limit * 100.0) if limit else 0.0

    def action_jeal_change_limit(self):
        """Abre el wizard para cambiar el límite de crédito con motivo."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Cambiar límite de crédito"),
            'res_model': 'jeal.credit.limit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_partner_id': self.id},
        }
