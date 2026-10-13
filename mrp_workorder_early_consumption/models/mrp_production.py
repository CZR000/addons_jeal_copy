import logging

from odoo import models
from odoo.tools.float_utils import float_is_zero

_logger = logging.getLogger(__name__)


class MrpProduction(models.Model):
    _inherit = 'mrp.production'

    def _woec_finished_valuation_missing(self):
        """Detecta si los componentes consumidos generaron valoración SVL pero
        los productos terminados no, lo que indica el problema típico al
        consumir componentes antes de finalizar la MO (consumo anticipado)."""
        self.ensure_one()

        company_currency = self.company_id.currency_id
        finished_moves = self.move_finished_ids.filtered(lambda m: m.state == 'done')
        finished_moves = finished_moves.filtered(
            lambda m: m.product_id.is_storable
            and getattr(m.product_id, 'valuation', False) == 'real_time'
        )
        if not finished_moves:
            return False

        consumed_moves = self.move_raw_ids.filtered(lambda m: m.state == 'done')
        consumed_moves = consumed_moves.filtered(
            lambda m: m.location_dest_id and m.location_dest_id.usage == 'production'
        )

        consumed_value = sum(consumed_moves.stock_valuation_layer_ids.mapped('value'))
        if float_is_zero(consumed_value, precision_rounding=company_currency.rounding):
            return False

        if any(not m.stock_valuation_layer_ids for m in finished_moves):
            return True

        finished_value = sum(finished_moves.stock_valuation_layer_ids.mapped('value'))
        if float_is_zero(finished_value, precision_rounding=company_currency.rounding):
            return True

        return False

    def _post_inventory(self, cancel_backorder=False):
        """Override que recalcula el costo del producto terminado cuando el
        consumo anticipado de componentes (por parte de este módulo) dejó a
        `_cal_price` upstream sin `consumed_moves` para calcular el costo.
        """
        res = super()._post_inventory(cancel_backorder=cancel_backorder)

        for production in self:
            if not production._woec_finished_valuation_missing():
                continue

            consumed_moves = production.move_raw_ids.filtered(lambda m: m.state == 'done')
            consumed_moves = consumed_moves.filtered(
                lambda m: m.location_dest_id and m.location_dest_id.usage == 'production'
            )
            if not consumed_moves:
                continue

            _logger.info(
                '[WOEC] Recomputing finished-goods valuation for MO %s(%s) using %s done raw moves (early-consumption correction).',
                production.name,
                production.id,
                len(consumed_moves),
            )
            production._cal_price(consumed_moves)

        return res

    def _woec_get_done_consumed_moves_for_cost(self):
        self.ensure_one()
        return self.move_raw_ids.filtered(
            lambda m: m.state == 'done'
            and not getattr(m, 'scrapped', False)
            and m.location_dest_id
            and m.location_dest_id.usage == 'production'
        )

    def _cal_price(self, consumed_moves):
        """Si vienen `consumed_moves` vacíos (porque ya se consumieron antes
        del finish standard), recuperamos los moves done de la MO para que
        `_cal_price` upstream pueda calcular el costo correctamente."""
        for production in self:
            cm = consumed_moves.filtered(lambda m: m.raw_material_production_id == production) if consumed_moves else self.env['stock.move']

            if not cm:
                cm = production._woec_get_done_consumed_moves_for_cost()
                _logger.info(
                    '[WOEC] _cal_price fallback: MO=%s(%s) consumed_moves was empty; using done raw moves=%s',
                    production.name, production.id, len(cm),
                )

            super(MrpProduction, production)._cal_price(cm)

        return True