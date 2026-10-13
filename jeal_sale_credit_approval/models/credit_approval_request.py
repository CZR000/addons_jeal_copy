# -*- coding: utf-8 -*-
import secrets
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError


class CreditApprovalRequest(models.Model):
    _name = 'jeal.credit.approval.request'
    _description = "Solicitud de aprobación de crédito"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string="Número", required=True, copy=False, readonly=True,
        default=lambda self: _("Nuevo"))
    order_id = fields.Many2one(
        'sale.order', string="Cotización", required=True,
        ondelete='cascade', index=True, tracking=True)
    partner_id = fields.Many2one(
        'res.partner', string="Cliente", required=True, tracking=True)
    company_id = fields.Many2one(
        'res.company', string="Compañía",
        default=lambda self: self.env.company)
    currency_id = fields.Many2one(
        related='company_id.currency_id', string="Moneda")
    user_id = fields.Many2one(
        'res.users', string="Vendedor", default=lambda self: self.env.user,
        tracking=True)
    approver_id = fields.Many2one('res.users', string="Aprobador", tracking=True)

    amount_pen = fields.Monetary(string="Importe de la cotización (S/)")
    debt_total = fields.Monetary(string="Deuda total")
    debt_overdue = fields.Monetary(string="Deuda vencida")
    credit_limit = fields.Monetary(string="Límite de crédito")
    excess = fields.Monetary(string="Exceso sobre el límite")
    reason_code = fields.Selection([
        ('excess', "Excede línea"),
        ('overdue', "Deuda vencida"),
        ('both', "Excede línea y deuda vencida"),
    ], string="Motivo de la solicitud", tracking=True)

    rejection_reason = fields.Text(string="Motivo del rechazo")
    state = fields.Selection([
        ('pending', "Pendiente"),
        ('approved', "Aprobada"),
        ('rejected', "Rechazada"),
        ('expired', "Vencida"),
    ], string="Estado", default='pending', tracking=True, copy=False)

    token = fields.Char(string="Token", copy=False, index=True, readonly=True)
    sent_date = fields.Datetime(string="Enviada", copy=False)
    expiry_date = fields.Datetime(string="Vence", copy=False, tracking=True)
    decided_date = fields.Datetime(string="Fecha de decisión", copy=False)

    # ------------------------------------------------------------------
    # Creación
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _("Nuevo")) == _("Nuevo"):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'jeal.credit.approval.request') or _("Nuevo")
            if not vals.get('token'):
                vals['token'] = secrets.token_urlsafe(32)
        return super().create(vals_list)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _is_valid(self):
        self.ensure_one()
        return (
            self.state == 'pending'
            and self.expiry_date
            and self.expiry_date >= fields.Datetime.now()
        )

    def _get_public_url(self, action):
        self.ensure_one()
        base = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        return "%s/credit/solicitud/%s?token=%s&action=%s" % (
            base, self.name.replace('/', '-'), self.token, action)

    def _send_request_mail(self):
        self.ensure_one()
        template = self.env.ref(
            'jeal_sale_credit_approval.mail_tmpl_credit_request',
            raise_if_not_found=False)
        if template and self.approver_id.email:
            template.send_mail(self.id, force_send=True)
        self.sent_date = fields.Datetime.now()

    def _notify_salesperson(self, template_xmlid):
        self.ensure_one()
        template = self.env.ref(template_xmlid, raise_if_not_found=False)
        if template and self.user_id.email:
            template.send_mail(self.id, force_send=True)

    # ------------------------------------------------------------------
    # Decisiones
    # ------------------------------------------------------------------
    def action_approve(self):
        for req in self:
            if not req._is_valid():
                raise UserError(_("Esta solicitud ya no está vigente."))
            req.write({
                'state': 'approved',
                'approver_id': self.env.user.id,
                'decided_date': fields.Datetime.now(),
            })
            req.order_id._jeal_apply_approval(req)
            req.order_id.message_post(body=_(
                "Crédito aprobado desde el correo · %(name)s · importe "
                "%(amount)s · exceso aprobado %(excess)s.",
                name=req.name,
                amount=req.currency_id.format(req.amount_pen),
                excess=req.currency_id.format(req.excess)))
            req._notify_salesperson(
                'jeal_sale_credit_approval.mail_tmpl_credit_approved')
        return True

    def action_reject(self, reason=None):
        for req in self:
            if not req._is_valid():
                raise UserError(_("Esta solicitud ya no está vigente."))
            motive = (reason or req.rejection_reason or '').strip()
            if not motive:
                raise UserError(_("El motivo del rechazo es obligatorio."))
            req.write({
                'state': 'rejected',
                'rejection_reason': motive,
                'approver_id': self.env.user.id,
                'decided_date': fields.Datetime.now(),
            })
            req.order_id._jeal_apply_rejection(req)
            req.order_id.message_post(body=_(
                "Crédito rechazado · %(name)s · Motivo: %(reason)s",
                name=req.name, reason=motive))
            req._notify_salesperson(
                'jeal_sale_credit_approval.mail_tmpl_credit_rejected')
        return True

    @api.model
    def _cron_expire_requests(self):
        now = fields.Datetime.now()
        expired = self.search([
            ('state', '=', 'pending'),
            ('expiry_date', '<', now),
        ])
        for req in expired:
            req.state = 'expired'
            req.order_id._jeal_apply_expiry(req)
            req.order_id.message_post(body=_(
                "La solicitud %(name)s venció sin respuesta. Se avisó al "
                "vendedor por correo.", name=req.name))
            req._notify_salesperson(
                'jeal_sale_credit_approval.mail_tmpl_credit_expired')
        return True
