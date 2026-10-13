from odoo import _, api, fields, models
from odoo.tools import date_utils


class ApprovalCategory(models.Model):
    _inherit = 'approval.category'

    is_expense_category = fields.Boolean(
        string='Aplica a Informe de Gastos',
        help='Si está marcado, esta categoría aparecerá en el menú "Solicitudes" '
             'del módulo de Gastos. Las categorías de Reclutamiento u otras que no '
             'correspondan a un desembolso no deben marcarse.',
    )

    approval_type = fields.Selection(
        selection_add=[('payment', 'Crear Pago a Proveedor')],
    )
    default_payment_journal_id = fields.Many2one(
        'account.journal',
        string='Diario de pago por defecto',
        domain="[('type', 'in', ('bank', 'cash')), ('company_id', '=', company_id)]",
        help='Diario propuesto al crear el pago desde una solicitud aprobada. '
             'El aprobador puede cambiarlo en el propio pago.',
    )
    default_payment_method_line_id = fields.Many2one(
        'account.payment.method.line',
        string='Método de pago por defecto',
        # El pago de una solicitud siempre es una salida de dinero: un método de
        # entrada lo registraría contra la cuenta de cobros pendientes.
        domain="[('journal_id', '=', default_payment_journal_id), ('payment_type', '=', 'outbound')]",
        help='Método de pago de salida propuesto al crear el pago desde una solicitud aprobada. '
             'El aprobador puede cambiarlo en el propio pago.',
    )
    default_means_payment_id = fields.Many2one(
        'payment.methods.codes',
        string='Medio de pago (libro de bancos) por defecto',
        help='Medio de pago SUNAT propuesto al crear el pago desde una solicitud aprobada '
             '(p.ej. "Depósito en cuenta"). Si se deja vacío, se usa el código 001 '
             '(Depósito en cuenta). El aprobador puede cambiarlo en el propio pago. '
             'Solo aplica si el módulo de libro de bancos (PLE) está instalado.',
    )

    # Padding configurable de la secuencia (el módulo "approvals" lo deja fijo en 5).
    sequence_padding = fields.Integer(
        string='Dígitos del correlativo',
        default=3,
        help='Cantidad de dígitos del correlativo generado por la secuencia, '
             'p.ej. 3 para "001". Solo aplica si "Secuencia Automática" está activo.',
    )

    # Defaults para que una categoría nueva ya venga con el correlativo
    # JE-AL/AÑO/MES/### armado, sin que el admin tenga que tipearlo cada vez.
    automated_sequence = fields.Boolean(default=True)
    sequence_code = fields.Char(default='JE-AL/%(year)s/%(month)s/')

    @api.onchange('default_payment_journal_id')
    def _onchange_default_payment_journal_id(self):
        if self.default_payment_method_line_id.journal_id != self.default_payment_journal_id:
            self.default_payment_method_line_id = False

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for record in records:
            if record.automated_sequence and record.sequence_id:
                record.sequence_id.write({
                    'padding': record.sequence_padding or 3,
                    'use_date_range': True,
                })
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'sequence_padding' in vals or 'sequence_code' in vals:
            for category in self:
                if category.sequence_id:
                    category.sequence_id.write({
                        'padding': vals.get('sequence_padding', category.sequence_padding) or 3,
                        'use_date_range': True,
                    })
        return res

    def _ensure_current_month_date_range(self):
        """Garantiza que exista un ir.sequence.date_range acotado al mes actual,
        para que el correlativo (JE-AL/2026/08/001) reinicie cada mes. Sin esto,
        `ir.sequence` con use_date_range=True igual funciona, pero el rango que
        crea automáticamente por defecto es de todo el año, no mensual."""
        today = fields.Date.context_today(self)
        month_start = date_utils.start_of(today, 'month')
        month_end = date_utils.end_of(today, 'month')
        for category in self:
            sequence = category.sequence_id
            if not sequence or not sequence.use_date_range:
                continue
            existing = self.env['ir.sequence.date_range'].sudo().search([
                ('sequence_id', '=', sequence.id),
                ('date_from', '<=', today),
                ('date_to', '>=', today),
            ], limit=1)
            if not existing:
                self.env['ir.sequence.date_range'].sudo().create({
                    'sequence_id': sequence.id,
                    'date_from': month_start,
                    'date_to': month_end,
                })
