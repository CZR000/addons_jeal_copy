from odoo import models, fields, api, _


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

    @api.depends('revaluation_entry_ids')
    def _compute_revaluation_entry_count(self):
        for move in self:
            move.revaluation_entry_count = len(move.revaluation_entry_ids)

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
