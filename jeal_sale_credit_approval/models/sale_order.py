# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError
from odoo.tools import float_compare


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    jeal_sale_type = fields.Selection([
        ('cash', "Contado"),
        ('credit', "Crédito"),
    ], string="Tipo de venta", default='credit', tracking=True,
        help="Solo las ventas al Crédito pasan por el control de línea de "
             "crédito. El Contado tiene pago previo.")

    jeal_company_currency_id = fields.Many2one(
        'res.currency', compute='_compute_jeal_credit_box')
    jeal_amount_pen = fields.Monetary(
        string="Esta cotización (S/)", compute='_compute_jeal_credit_box',
        currency_field='jeal_company_currency_id')
    jeal_credit_limit = fields.Monetary(
        string="Límite de crédito", compute='_compute_jeal_credit_box',
        currency_field='jeal_company_currency_id')
    jeal_debt_total = fields.Monetary(
        string="Deuda total", compute='_compute_jeal_credit_box',
        currency_field='jeal_company_currency_id')
    jeal_debt_overdue = fields.Monetary(
        string="Deuda vencida", compute='_compute_jeal_credit_box',
        currency_field='jeal_company_currency_id')
    jeal_credit_available = fields.Monetary(
        string="Disponible", compute='_compute_jeal_credit_box',
        currency_field='jeal_company_currency_id')
    jeal_excess = fields.Monetary(
        string="Exceso", compute='_compute_jeal_credit_box',
        currency_field='jeal_company_currency_id')
    jeal_requires_approval = fields.Boolean(
        string="Requiere aprobación", compute='_compute_jeal_credit_box')

    jeal_approval_state = fields.Selection([
        ('none', "Sin aprobación"),
        ('pending', "Pendiente de aprobación"),
        ('approved', "Crédito aprobado"),
        ('rejected', "Crédito rechazado"),
        ('expired', "Solicitud vencida"),
    ], string="Estado de aprobación", default='none', copy=False, tracking=True)
    jeal_approved_amount = fields.Monetary(
        string="Importe aprobado", copy=False,
        currency_field='jeal_company_currency_id')
    jeal_request_ids = fields.One2many(
        'jeal.credit.approval.request', 'order_id', string="Solicitudes")
    jeal_request_count = fields.Integer(compute='_compute_request_count')

    def _compute_request_count(self):
        for order in self:
            order.jeal_request_count = len(order.jeal_request_ids)

    def _jeal_amount_in_company_currency(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        if self.currency_id == company.currency_id:
            return self.amount_total
        return self.currency_id._convert(
            self.amount_total, company.currency_id, company,
            fields.Date.context_today(self))

    @api.depends('partner_id', 'amount_total', 'currency_id', 'jeal_sale_type',
                 'jeal_approval_state')
    def _compute_jeal_credit_box(self):
        for order in self:
            company = order.company_id or self.env.company
            order.jeal_company_currency_id = company.currency_id
            partner = order.partner_id
            amount_pen = order._jeal_amount_in_company_currency() if partner else 0.0
            limit = partner.jeal_credit_limit if partner else 0.0
            debt = partner.jeal_debt_total if partner else 0.0
            overdue = partner.jeal_debt_overdue if partner else 0.0
            projected = debt + amount_pen
            excess = max(projected - limit, 0.0) if limit else projected

            needs = False
            if order.jeal_sale_type == 'credit' and partner:
                if not limit:
                    needs = True
                elif float_compare(projected, limit,
                                   precision_rounding=company.currency_id.rounding) > 0:
                    needs = True
                if company.jeal_require_approval_overdue and overdue > 0:
                    needs = True

            order.jeal_amount_pen = amount_pen
            order.jeal_credit_limit = limit
            order.jeal_debt_total = debt
            order.jeal_debt_overdue = overdue
            order.jeal_credit_available = limit - debt
            order.jeal_excess = excess
            order.jeal_requires_approval = needs

    # ------------------------------------------------------------------
    # Bloqueo en la confirmación
    # ------------------------------------------------------------------
    def _jeal_check_credit(self):
        self.ensure_one()
        if self.jeal_sale_type != 'credit' or not self.jeal_requires_approval:
            return
        company = self.company_id or self.env.company
        rounding = company.currency_id.rounding
        if self.jeal_approval_state == 'approved':
            # Re-aprobación solo si el importe subió respecto a lo aprobado.
            if float_compare(self.jeal_amount_pen, self.jeal_approved_amount,
                             precision_rounding=rounding) <= 0:
                return
            self.jeal_approval_state = 'none'
            self.jeal_approved_amount = 0.0
            raise UserError(_(
                "El importe subió por encima de lo aprobado. Debe enviar una "
                "nueva solicitud de aprobación de crédito."))
        raise UserError(_(
            "La cotización no puede confirmarse: requiere aprobación de "
            "crédito. Use el botón «Enviar solicitud al aprobador»."))

    def action_confirm(self):
        for order in self:
            order._jeal_check_credit()
        return super().action_confirm()

    # ------------------------------------------------------------------
    # Envío / reenvío de solicitud
    # ------------------------------------------------------------------
    def action_jeal_open_send_wizard(self):
        self.ensure_one()
        if not self.jeal_requires_approval:
            raise UserError(_("Esta cotización no requiere aprobación de crédito."))
        return {
            'type': 'ir.actions.act_window',
            'name': _("Se requiere aprobación de crédito"),
            'res_model': 'jeal.credit.approval.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_order_id': self.id},
        }

    def _jeal_create_and_send_request(self):
        self.ensure_one()
        company = self.company_id or self.env.company
        approver = company.jeal_credit_approver_id
        if not approver:
            raise UserError(_(
                "No se ha configurado el aprobador de crédito en Ventas › "
                "Ajustes. Configúrelo antes de enviar solicitudes."))
        if not approver.email:
            raise UserError(_(
                "El aprobador de crédito no tiene correo configurado."))

        # Anula cualquier solicitud pendiente previa de esta cotización.
        self.jeal_request_ids.filtered(
            lambda r: r.state == 'pending').write({'state': 'expired'})

        overdue = self.jeal_debt_overdue > 0
        excess = self.jeal_excess > 0
        reason = 'both' if (overdue and excess) else (
            'overdue' if overdue else 'excess')
        hours = company.jeal_link_validity_hours or 72
        request = self.env['jeal.credit.approval.request'].create({
            'order_id': self.id,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'approver_id': approver.id,
            'amount_pen': self.jeal_amount_pen,
            'debt_total': self.jeal_debt_total,
            'debt_overdue': self.jeal_debt_overdue,
            'credit_limit': self.jeal_credit_limit,
            'excess': self.jeal_excess,
            'reason_code': reason,
            'expiry_date': fields.Datetime.now() + timedelta(hours=hours),
        })
        request._send_request_mail()
        self.jeal_approval_state = 'pending'
        self.message_post(body=_(
            "Solicitud de aprobación de crédito %(name)s enviada a %(approver)s. "
            "Motivo: %(reason)s. Importe %(amount)s · deuda total %(debt)s · "
            "límite %(limit)s · exceso %(excess)s.",
            name=request.name, approver=approver.name,
            reason=dict(request._fields['reason_code'].selection).get(reason),
            amount=self.currency_id.format(self.jeal_amount_pen),
            debt=self.currency_id.format(self.jeal_debt_total),
            limit=self.currency_id.format(self.jeal_credit_limit),
            excess=self.currency_id.format(self.jeal_excess)))
        return request

    def action_jeal_resend_request(self):
        self.ensure_one()
        if not self.jeal_requires_approval:
            raise UserError(_("Esta cotización ya no requiere aprobación."))
        self._jeal_create_and_send_request()
        return True

    # ------------------------------------------------------------------
    # Callbacks desde la solicitud
    # ------------------------------------------------------------------
    def _jeal_apply_approval(self, request):
        self.ensure_one()
        self.write({
            'jeal_approval_state': 'approved',
            'jeal_approved_amount': request.amount_pen,
        })

    def _jeal_apply_rejection(self, request):
        self.ensure_one()
        self.jeal_approval_state = 'rejected'

    def _jeal_apply_expiry(self, request):
        self.ensure_one()
        if self.jeal_approval_state == 'pending':
            self.jeal_approval_state = 'expired'

    def action_jeal_view_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _("Solicitudes de aprobación"),
            'res_model': 'jeal.credit.approval.request',
            'view_mode': 'list,form',
            'domain': [('order_id', '=', self.id)],
        }
