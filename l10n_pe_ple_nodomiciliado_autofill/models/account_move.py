# -*- coding: utf-8 -*-
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Tipos de comprobante que SUNAT acepta en el campo 10 del RCE No Domiciliados
# (tipo de comprobante que sustenta el credito fiscal).
NODOM_SUSTENTO_ALLOWED_CODES = ('00', '46', '50', '51', '52', '53')


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Tipo de documento que sustenta el credito fiscal (campo 10 del TXT).
    # Ya no se autorrellena: lo elige el usuario y solo admite los codigos
    # permitidos por SUNAT.
    # copy=False: el sustento es propio de cada factura y no debe heredarse al
    # duplicar (ademas, una factura antigua con 91 haria fallar la copia).
    inv_type_document = fields.Many2one(
        domain=[
            ('code', 'in', NODOM_SUSTENTO_ALLOWED_CODES),
            ('country_id.code', '=', 'PE'),
        ],
        copy=False,
    )
    inv_serie = fields.Char(copy=False)
    inv_year_dua_dsi = fields.Char(copy=False)
    inv_correlative = fields.Char(copy=False)

    # Tipo de documento del propio comprobante (campo 4 del TXT): se mantiene
    # el 91 para No Domiciliado, pero respetando el calculo estandar de Odoo
    # para el resto de facturas.
    l10n_latam_document_type_id = fields.Many2one(
        compute='_compute_l10n_latam_document_type_id_nodom',
        store=True,
        readonly=False,
    )

    def _nodom_document_type_depends(self):
        base_method = getattr(type(self), '_compute_l10n_latam_document_type', None)
        depends = getattr(base_method, '_depends', ()) if base_method else ()
        if callable(depends):
            depends = depends(self)
        return tuple(depends) + ('is_nodomicilied',)

    @api.depends(lambda self: self._nodom_document_type_depends())
    def _compute_l10n_latam_document_type_id_nodom(self):
        # Primero el calculo estandar (l10n_latam_invoice_document y herencias).
        if hasattr(self, '_compute_l10n_latam_document_type'):
            self._compute_l10n_latam_document_type()
        nodom_moves = self.filtered('is_nodomicilied')
        if not nodom_moves:
            return
        doc_91 = self.env['l10n_latam.document.type'].search(
            [('code', '=', '91'), ('country_id.code', '=', 'PE')],
            limit=1,
        )
        if doc_91:
            nodom_moves.l10n_latam_document_type_id = doc_91

    @api.constrains('is_nodomicilied', 'inv_type_document')
    def _check_nodom_inv_type_document(self):
        for move in self:
            if (
                move.is_nodomicilied
                and move.inv_type_document
                and move.inv_type_document.code not in NODOM_SUSTENTO_ALLOWED_CODES
            ):
                raise ValidationError(_(
                    "Factura %(move)s: el tipo de documento que sustenta el "
                    "crédito fiscal (pestaña No Domiciliado) debe ser uno de "
                    "%(codes)s según SUNAT. Valor actual: (%(code)s) %(name)s.",
                    move=move.display_name,
                    codes=', '.join(NODOM_SUSTENTO_ALLOWED_CODES),
                    code=move.inv_type_document.code,
                    name=move.inv_type_document.name,
                ))
