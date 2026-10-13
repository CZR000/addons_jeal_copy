# -*- coding: utf-8 -*-
from odoo import api, fields, models


class AccountMove(models.Model):
    _inherit = 'account.move'

    inv_serie = fields.Char(
        compute='_compute_inv_serie_correlative',
        store=True,
        readonly=False,
    )
    inv_correlative = fields.Char(
        compute='_compute_inv_serie_correlative',
        store=True,
        readonly=False,
    )
    inv_type_document = fields.Many2one(
        compute='_compute_inv_type_document',
        store=True,
        readonly=False,
    )
    l10n_latam_document_type_id = fields.Many2one(
        compute='_compute_l10n_latam_document_type_id_nodom',
        store=True,
        readonly=False,
    )

    @staticmethod
    def _split_ref_serie_correlative(ref):
        if not ref:
            return None, None
        ref = ref.strip()
        if '-' in ref:
            serie, correlative = ref.split('-', 1)
            return serie.strip() or None, correlative.strip() or None
        return '', ref or None
    
    @api.depends('is_nodomicilied', 'ref')
    def _compute_inv_serie_correlative(self):
        for move in self:
            if not move.is_nodomicilied:
                continue
            serie, correlative = move._split_ref_serie_correlative(move.ref)
            if serie is not None:
                move.inv_serie = serie
            if correlative is not None:
                move.inv_correlative = correlative

    @api.depends('is_nodomicilied')
    def _compute_inv_type_document(self):
        doc_91 = self.env['l10n_latam.document.type'].search(
            [('code', '=', '91'), ('country_id.code', '=', 'PE')],
            limit=1,
        )
        for move in self:
            if move.is_nodomicilied and doc_91:
                move.inv_type_document = doc_91

    @api.depends('is_nodomicilied')
    def _compute_l10n_latam_document_type_id_nodom(self):
        doc_91 = self.env['l10n_latam.document.type'].search(
            [('code', '=', '91'), ('country_id.code', '=', 'PE')],
            limit=1,
        )
        for move in self:
            if move.is_nodomicilied and doc_91:
                move.l10n_latam_document_type_id = doc_91