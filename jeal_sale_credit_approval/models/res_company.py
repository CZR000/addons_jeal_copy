# -*- coding: utf-8 -*-
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    jeal_credit_approver_id = fields.Many2one(
        'res.users',
        string="Aprobador de crédito",
        help="Usuario único que recibe por correo las solicitudes de "
             "aprobación de ventas al crédito. Debe tener un correo válido.",
    )
    jeal_link_validity_hours = fields.Integer(
        string="Vigencia del enlace (horas)",
        default=72,
        help="Horas durante las cuales funcionan los botones Aprobar / "
             "Rechazar del correo. Vencido, el vendedor reenvía la solicitud.",
    )
    jeal_require_approval_overdue = fields.Boolean(
        string="Exigir aprobación con deuda vencida",
        default=True,
        help="Si el cliente tiene cualquier factura vencida, la venta al "
             "crédito pide aprobación aunque esté dentro del límite.",
    )
    # --- Composición de la deuda total (punto a validar con el cliente) ---
    jeal_debt_include_draft = fields.Boolean(
        string="Incluir facturas en borrador",
        default=True,
    )
    jeal_debt_include_so_unbilled = fields.Boolean(
        string="Incluir pedidos confirmados sin facturar",
        default=True,
    )
    jeal_debt_subtract_advances = fields.Boolean(
        string="Restar anticipos sin aplicar",
        default=True,
    )
