import logging
import time

from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    revaluation_source_move_id = fields.Many2one(
        comodel_name='account.move',
        string='Revaluation Source Document',
        readonly=True,
        copy=False,
        index=True,
        help='The original document (invoice, bill, journal entry) for which '
             'this revaluation adjustment was created.',
    )
    revaluation_entry_ids = fields.One2many(
        comodel_name='account.move',
        inverse_name='revaluation_source_move_id',
        string='Revaluation Entries',
        readonly=True,
    )
    revaluation_entry_count = fields.Integer(
        compute='_compute_revaluation_entry_count',
        string='# Revaluation Entries',
    )
    # Set only on adjustment entries created in draft by the revaluation wizard.
    # When such an entry is posted (one by one or in batch), its reversal is
    # created and posted automatically using these values.
    revaluation_reversal_date = fields.Date(
        string='Revaluation Reversal Date',
        readonly=True,
        copy=False,
    )
    revaluation_fiscal_closure = fields.Boolean(
        string='Revaluation Fiscal Closure',
        readonly=True,
        copy=False,
    )

    @api.depends('revaluation_entry_ids')
    def _compute_revaluation_entry_count(self):
        for move in self:
            move.revaluation_entry_count = len(move.revaluation_entry_ids)

    # -------------------------------------------------------------------------
    # Automatic reversal of draft revaluation entries
    # -------------------------------------------------------------------------

    def _post(self, soft=True):
        posted = super()._post(soft=soft)
        to_reverse = posted.filtered(
            lambda m: m.state == 'posted'
            and m.revaluation_reversal_date
            and not m.reversed_entry_id
        )
        if to_reverse:
            # Skip entries already reversed (e.g. reset to draft and posted again)
            already_reversed = self.search([('reversed_entry_id', 'in', to_reverse.ids)]).reversed_entry_id
            to_reverse -= already_reversed
        if to_reverse:
            to_reverse._create_revaluation_reversals()
        return posted

    def _create_revaluation_reversals(self):
        """Create and post the reversal of each revaluation adjustment in ``self``."""
        t0 = time.time()
        default_values_list = [
            {
                'ref': _("Reversal of: %s", move.ref),
                'date': move.revaluation_reversal_date,
                'revaluation_source_move_id': move.revaluation_source_move_id.id,
            }
            for move in self
        ]
        reverse_moves = self._reverse_moves(default_values_list=default_values_list)
        reverse_moves.action_post()

        closure_reversals = reverse_moves.filtered(lambda r: r.reversed_entry_id.revaluation_fiscal_closure)
        if closure_reversals:
            closure_reversals.button_draft()
            closure_reversals.button_cancel()

        _logger.info(
            "Revaluation: created %d automatic reversals in %.2fs",
            len(reverse_moves), time.time() - t0,
        )
        return reverse_moves

    # -------------------------------------------------------------------------
    # Smart buttons
    # -------------------------------------------------------------------------

    def action_open_revaluation_entries(self):
        """Open the revaluation entries linked to this source document."""
        self.ensure_one()
        list_view = self.env.ref('account.view_move_tree', False)
        form_view = self.env.ref('account.view_move_form', False)
        action = {
            'name': _("Revaluation Entries"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'domain': [('id', 'in', self.revaluation_entry_ids.ids)],
            'view_mode': 'list,form',
            'views': [
                (list_view and list_view.id or False, 'list'),
                (form_view and form_view.id or False, 'form'),
            ],
            'context': dict(self.env.context, create=False),
        }
        if self.revaluation_entry_count == 1:
            action['view_mode'] = 'form'
            action['views'] = [(form_view and form_view.id or False, 'form')]
            action['res_id'] = self.revaluation_entry_ids.id
        return action

    def action_open_source_revaluation_move(self):
        """Open the source document from which this revaluation entry was created."""
        self.ensure_one()
        form_view = self.env.ref('account.view_move_form', False)
        return {
            'name': _("Source Document"),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.revaluation_source_move_id.id,
            'view_mode': 'form',
            'views': [(form_view and form_view.id or False, 'form')],
        }
