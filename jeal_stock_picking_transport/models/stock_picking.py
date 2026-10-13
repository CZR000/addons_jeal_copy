# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    transportista_id = fields.Many2one(
        'res.partner',
        string='Transportista',
    )
    guias_grr = fields.Char(
        string='Guías GRR',
        help='Guía de Remisión Remitente. Ejemplo: T001-00001234',
    )
    guias_gtr = fields.Char(
        string='Guías GTR',
        help='Guía de Remisión Transportista. Ejemplo: EOO1-09876543',
    )
    placa = fields.Char(
        string='Placa',
    )
    ticket_pesaje = fields.Char(
        string='Ticket de pesaje',
        help='Solo números. Ejemplo: 27781',
    )

    @api.constrains('ticket_pesaje')
    def _check_ticket_pesaje(self):
        for rec in self:
            if rec.ticket_pesaje and not rec.ticket_pesaje.strip().isdigit():
                raise ValidationError(
                    'El Ticket de pesaje solo puede contener números. '
                    'Valor ingresado: "%s"' % rec.ticket_pesaje
                )
