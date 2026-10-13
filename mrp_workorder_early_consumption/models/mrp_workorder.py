# -*- coding: utf-8 -*-
import logging

from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero

_logger = logging.getLogger(__name__)


class MrpWorkorder(models.Model):
    _inherit = 'mrp.workorder'

    def _woec_get_wo_component_moves(self):
        """Devuelve los stock.move asociados a esta WO. Si no hay moves
        directos en `move_raw_ids` de la WO pero sí los hay en la MO con la
        misma operation_id sin asignar a ninguna WO, los reclama escribiendo
        `workorder_id`."""
        self.ensure_one()

        moves = self.move_raw_ids.filtered(lambda m: m.state not in ('done', 'cancel'))
        if moves:
            return moves

        if not self.production_id or not self.operation_id:
            return self.env['stock.move'].browse()

        mo_moves = self.production_id.move_raw_ids.filtered(
            lambda m: m.state not in ('done', 'cancel')
            and m.operation_id == self.operation_id
            and not m.workorder_id
        )
        if mo_moves:
            _logger.info(
                "[WOEC] Claiming raw moves %s from MO %s to WO %s(%s) for native visibility.",
                mo_moves.ids, self.production_id.name, self.display_name, self.id
            )
            mo_moves.write({'workorder_id': self.id})
        return mo_moves

    def _woec_set_qty_done_if_needed(self, move):
        """
        Marca la cantidad realizada del move si está pendiente.
        """
        if move.state in ('done', 'cancel'):
            return

        if not float_is_zero(move.quantity, precision_rounding=move.product_uom.rounding):
            return

        if move.product_id.tracking != 'none':
            raise UserError(_(
                "No se puede finalizar la orden de trabajo '%(wo)s' de la "
                "fabricación '%(mo)s': el producto '%(product)s' requiere "
                "lote/serie. Registra los lotes/series (en la tablet / "
                "trazabilidad) antes de finalizar la orden de trabajo."
            ) % {
                'wo': self.display_name,
                'mo': self.production_id.name,
                'product': move.product_id.display_name,
            })

        qty = move.product_uom_qty
        if float_is_zero(qty, precision_rounding=move.product_uom.rounding):
            return

        if hasattr(move, '_set_quantity_done'):
            move._set_quantity_done(qty)
        else:
            move.quantity = qty

    def _woec_confirm_assign_and_done(self, moves):
        """Confirma, asigna y ejecuta _action_done sobre los moves de la WO.

        Política de error: si _action_done falla (falta de stock, cuenta
        contable no configurada, error de valoración, etc.), el error se
        propaga con contexto enriquecido (WO + MO) para que el operario
        pueda identificar dónde intervenir. NO se degrada silenciosamente
        al flujo nativo — un fallo silencioso escondería problemas de
        configuración cuyo efecto (analítica mal imputada, valoración
        descuadrada) sólo se detectaría meses después.
        """
        moves = moves.filtered(lambda m: m.state not in ('done', 'cancel'))
        if not moves:
            _logger.info('[WOEC] Nothing to consume for WO %s (no pending moves)', self.id)
            return

        _logger.info(
            '[WOEC] Processing moves for WO %s: %s',
            self.id, ', '.join([f'{m.id}:{m.state}' for m in moves])
        )

        moves_to_confirm = moves.filtered(lambda m: m.state == 'draft')
        if moves_to_confirm:
            moves_to_confirm._action_confirm()

        moves_to_assign = moves.filtered(lambda m: m.state in ('confirmed', 'waiting', 'partially_available'))
        if moves_to_assign:
            moves_to_assign._action_assign()

        for m in moves:
            self._woec_set_qty_done_if_needed(m)

        try:
            moves.with_context(woec_force_valuation=True)._action_done()
        except UserError:
            raise
        except Exception as e:
            _logger.exception(
                '[WOEC] _action_done failed for WO %s(%s) MO %s',
                self.display_name, self.id, self.production_id.name
            )
            raise UserError(_(
                "No se pudo consumir anticipadamente los componentes de "
                "la orden de trabajo '%(wo)s' de la fabricación '%(mo)s'.\n\n"
                "Detalle técnico: %(error)s\n\n"
                "Revisa la configuración (stock disponible, cuentas "
                "contables del producto, ubicaciones) y volvé a intentar."
            ) % {
                'wo': self.display_name,
                'mo': self.production_id.name,
                'error': str(e),
            }) from e

        _logger.info(
            '[WOEC] Moves done for WO %s: %s',
            self.id, ', '.join([f'{m.id}:{m.state}' for m in moves])
        )

    def _woec_early_consume_on_finish(self):
        for wo in self.filtered(lambda w: w.state not in ('done', 'cancel')):
            if not wo.production_id:
                _logger.warning('[WOEC] Skipping WO %s: no production_id', wo.id)
                continue
            if wo.production_id.state in ('done', 'cancel'):
                _logger.info(
                    '[WOEC] Skipping WO %s: MO %s state is %s',
                    wo.id, wo.production_id.name, wo.production_id.state
                )
                continue

            moves = wo._woec_get_wo_component_moves()
            wo._woec_confirm_assign_and_done(moves)

    def button_finish(self):
        _logger.info('[WOEC] button_finish called for WOs=%s', self.ids)
        self._woec_early_consume_on_finish()
        return super().button_finish()

    def button_done(self):
        _logger.info('[WOEC] button_done called for WOs=%s', self.ids)
        self._woec_early_consume_on_finish()
        return super().button_done()