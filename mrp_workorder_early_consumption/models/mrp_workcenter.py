# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MrpWorkcenter(models.Model):
    _inherit = 'mrp.workcenter'

    wo_consumable_line_ids = fields.One2many(
        comodel_name='mrp.workcenter.consumable',
        inverse_name='workcenter_id',
        string='Consumibles de centro de trabajo',
    )


class MrpWorkcenterConsumable(models.Model):
    _name = 'mrp.workcenter.consumable'
    _description = 'Workcenter Consumable'
    _order = 'sequence, id'
    _check_company_auto = True

    sequence = fields.Integer(default=10)
    workcenter_id = fields.Many2one(
        comodel_name='mrp.workcenter',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
    )
    company_id = fields.Many2one(
        comodel_name='res.company',
        related='workcenter_id.company_id',
        store=True,
        readonly=True,
    )
    product_id = fields.Many2one(
        comodel_name='product.product',
        required=True,
        check_company=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name='uom.uom',
        related='product_id.uom_id',
        readonly=True,
    )
    qty_per_unit = fields.Float(
        string='Cantidad por unidad producida',
        default=0.0,
    )
    qty_fixed = fields.Float(
        string='Cantidad fija por orden de trabajo',
        default=0.0,
    )

    @api.constrains('qty_per_unit', 'qty_fixed')
    def _check_qty(self):
        for rec in self:
            if rec.qty_per_unit < 0 or rec.qty_fixed < 0:
                raise ValidationError(_('Quantities cannot be negative.'))

    @api.constrains('product_id')
    def _check_product(self):
        for rec in self:
            if not rec.product_id:
                continue
            if rec.product_id.type == 'service':
                raise ValidationError(_('Service products cannot be consumed through stock moves.'))

    def _get_qty_to_consume(self, workorder):
        self.ensure_one()
        produced_qty = workorder._woec_get_produced_qty()
        return (produced_qty * self.qty_per_unit) + self.qty_fixed
