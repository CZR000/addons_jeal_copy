from odoo import fields, models, api

# Tasa de retención de renta por defecto para no domiciliados (Art. 76 LIR).
# La Renta Neta Presunta (Art. 48°) la sobrescribe con su propio porcentaje.
DEFAULT_NODOMICILIED_RETENTION_RATE = 30.0


class AccountMove(models.Model):
    _inherit = 'account.move'

    igv_withholding_indicator = fields.Boolean(
        string='Indicador de retención del IGV o Renta en Compras',
        help='Si el campo se activa, de forma automática aparece el en registro de compras'
             ' que el comprobante de pago registrado está afecto a retención del IGV, Renta o ambas inclusive'
    )
    inv_id = fields.Many2one(
        string='C. P. Sustento',
        comodel_name='account.move',
        domain=[('state', 'not in', ['draft', 'cancel'])]
    )
    inv_type_document = fields.Many2one(
        comodel_name='l10n_latam.document.type',
        string='Tipo documento',
        help='Tipo de Comprobante de Pago o Documento que sustenta el crédito fiscal.'
    )
    inv_serie = fields.Char(
        string='Serie de Comprabante',
        help='Serie del comprobante de pago o documento que sustenta el crédito fiscal.'
             'En los casos de la Declaración Única de Aduanas (DUA) o de la '
             'Declaración Simplificada de Importación (DSI) se consignará el código de la dependencia Aduanera.'
    )
    inv_correlative = fields.Char(
        string='Correlativo de Comprobante',
        help='Número del comprobante de pago o documento o número de orden del formulario físico o virtual'
             ' donde conste el pago del impuesto, tratándose de la utilización de servicios prestados por'
             ' no domiciliados u otros, número de la DUA o de la DSI, que sustente el crédito fiscal.'
    )
    inv_year_dua_dsi = fields.Char(
        string='Año emisión  DUA o DSI',
        size=4,
        help='Año de emisión de la DUA o DSI que sustenta el crédito fiscal. Odoo valida que en este campo se '
             'registre número mayor a  1981 y menor o igual al año del periodo informado'
    )
    inv_retention_igv = fields.Float(
        string='Monto retención de IGV',
        digits=(12, 2),
        help='Monto de retención del IGV'
    )
    is_nodomicilied = fields.Boolean(
        string='No Domiciliado',
        compute='_compute_is_nodomicilied',
        store=True,
        readonly=False,
    )
    linkage_id = fields.Many2one(
        comodel_name='link.economic',
        string='Vinculación',
        help='Vínculo entre el contribuyente y el residente en el extranjero.'
             'Se completan de acuerdo a la tabla 27 del Anexo 2 de SUNAT.'
    )
    hard_rent = fields.Float(
        string='Renta Bruta',
        digits=(12, 2),
        compute='_compute_hard_rent',
        store=True,
        readonly=False,
        help='Importe bruto de la factura (base imponible) expresado en la moneda '
             'de la compañía, es decir convertido con el tipo de cambio de la factura.'
    )
    deduccion_cost = fields.Float(
        string='Deducción/Costo',
        digits=(12, 2),
        help='Deducción o costo asociado a la renta bruta. Se ingresa manualmente '
             'y se resta de la Renta Bruta para obtener la Renta Neta.'
    )
    neto_rent = fields.Float(
        string='Renta Neta',
        digits=(12, 2),
        compute='_compute_neto_rent',
        store=True,
        help='Diferencia entre la Renta Bruta y la Deducción/Costo.'
    )
    retention_rate = fields.Float(
        string='Tasa de Retención',
        digits=(5, 2),
        compute='_compute_retention_rate',
        store=True,
        readonly=False,
        help='Porcentaje aplicado sobre la Renta Neta. Toma el porcentaje de la '
             'actividad de Renta Neta Presunta (Art. 48°) cuando se selecciona una; '
             'en caso contrario usa la tasa por defecto de no domiciliado (30%). '
             'Se puede editar manualmente.'
    )
    presumed_net_income_id = fields.Many2one(
        comodel_name='presumed.net.income',
        string='Renta Neta Presunta (Art. 48°)',
        help='Actividad del Art. 48 de la Ley del Impuesto a la Renta. '
             'Si se selecciona, la Tasa de Retención toma el porcentaje presunto '
             'de la actividad. Si se deja vacío, la tasa usa el 30% por defecto '
             'de no domiciliado.'
    )
    tax_withheld = fields.Float(
        string='Impuesto retenido',
        digits=(12, 2),
        compute='_compute_tax_withheld',
        store=True,
        help='Renta Neta multiplicada por la Tasa de Retención.'
    )
    cdi = fields.Selection(
        string='CDI',
        selection=[
            ("00", "NINGUNO"),
            ("01", "CANADA"),
            ("02", "CHILE"),
            ("03", "COMUNIDAD ANDINA DE NACIONES (CAN)"),
            ("04", "BRASIL"),
            ("05", "ESTADOS UNIDOS MEXICANOS"),
            ("06", "REPUBLICA DE COREA"),
            ("07", "CONFEDERACIÓN SUIZA"),
            ("08", "PORTUGAL"),
            ("09", "OTROS")
        ],
        help='Convenios para evitar la doble imposición.'
             'Es campo se autocompleta con el campo “Código de Convenio para evitar doble imposición”.'
             'Se completan de acuerdo a la tabla 25 del Anexo 2 de SUNAT.'
    )
    exoneration_nodomicilied_id = fields.Many2one(
        comodel_name='exoneration.nodomicilied',
        string='Exoneracion de No Domiciliado'
    )
    type_rent_id = fields.Many2one(
        comodel_name='type.rent',
        string='Tipo de Renta'
    )
    taken_id = fields.Many2one(
        string='Modalidad de servicio prestado',
        comodel_name='service.taken'
    )
    application_article = fields.Char(
        string='Aplicación Art. 76°',
        help='Consignar 1 si aplica, sino se queda en Blanco. '
             '(Aplicación del penúltimo párrafo del Art. 76° de la Ley del Impuesto a la Renta)'
    )

    types_goods_services_id = fields.Many2one(
        comodel_name='classification.services',
        string='Clasificación de los bienes y servicios adquiridos'
    )

    @api.depends('company_id', 'partner_id')
    def _compute_is_nodomicilied(self):
        for obj in self:
            if obj.partner_id and obj.company_id.country_id == self.env.ref('base.pe'):
                if obj.partner_id.country_id and obj.partner_id.country_id == obj.company_id.country_id:
                    obj.is_nodomicilied = False
                elif not obj.partner_id.country_id:
                    obj.is_nodomicilied = False
                else:
                    obj.is_nodomicilied = True


    @api.model_create_multi
    def create(self, values):
        r = super(AccountMove, self).create(values)
        for move in r:
            if move.move_type in ['out_invoice', 'out_refund']:
                move.ple_state = '1'
            elif move.move_type in ['in_invoice', 'in_refund']:
                zero_taxes = 0
                for line in move.invoice_line_ids:
                    for tax in line.tax_ids:
                        if tax.amount == 0.00:
                            zero_taxes += 1

                if move.is_nodomicilied or zero_taxes == len(move.invoice_line_ids):
                    move.ple_state = '0'
                elif move.ple_date and move.invoice_date and move.invoice_date.month < move.ple_date.month or (
                        move.invoice_date and move.invoice_date.year < move.ple_date.year):
                    move.ple_state = '6'
                else:
                    move.ple_state = '1'
        return r

    @api.model
    def _get_view(self, view_id=None, view_type='form', **options):
        arch, view = super()._get_view(view_id, view_type, **options)
        if view_type in ('form'):
            tags = [('field', 'is_nodomicilied'), ('field', 'bool_pay_invoice')]
            arch, view = self.env['res.partner']._tags_invisible_per_country(arch, view, tags, [self.env.ref('base.pe')])
        return arch, view

    @api.onchange('date')
    def onchange_ple_date_from_date(self):
        self.ple_date = self.date
        self.validation_ple_state()

    @api.onchange('invoice_date')
    def onchange_date_from_invoice_date(self):
        if self.invoice_date:
            self.date = self.invoice_date
            self.validation_ple_state()

    @api.onchange('invoice_line_ids')
    def onchange_invoice_line_ids_validation_ple(self):
        if self.invoice_line_ids:
            self.validation_ple_state()

    def validation_ple_state(self):
        taxes_diff = 0
        for line in self.invoice_line_ids:
            for tax in line.tax_ids:
                if tax.amount == 0.00:
                    taxes_diff += 1
        if self.is_nodomicilied or taxes_diff == len(self.invoice_line_ids):
            self.ple_state = '0'
        elif self.invoice_date and self.date:
            if self.invoice_date.month < self.date.month or self.invoice_date.year < self.date.year:
                self.ple_state = '6'
            else:
                self.ple_state = '1'
        else:
            self.ple_state = '1'

    @api.depends('is_nodomicilied', 'amount_untaxed_signed')
    def _compute_hard_rent(self):
        for move in self:
            if not move.is_nodomicilied:
                move.hard_rent = 0.00
                continue
            # amount_untaxed_signed ya está en la moneda de la compañía, es decir
            # convertido con el tipo de cambio de la factura, y es negativo en
            # facturas de proveedor.
            move.hard_rent = abs(move.amount_untaxed_signed)

    @api.depends('is_nodomicilied', 'hard_rent', 'deduccion_cost')
    def _compute_neto_rent(self):
        for move in self:
            if not move.is_nodomicilied:
                move.neto_rent = 0.00
                continue
            move.neto_rent = move.hard_rent - move.deduccion_cost

    @api.depends('is_nodomicilied', 'presumed_net_income_id.percentage')
    def _compute_retention_rate(self):
        for move in self:
            if not move.is_nodomicilied:
                move.retention_rate = 0.00
            elif move.presumed_net_income_id:
                move.retention_rate = move.presumed_net_income_id.percentage
            else:
                move.retention_rate = DEFAULT_NODOMICILIED_RETENTION_RATE

    @api.depends('is_nodomicilied', 'neto_rent', 'retention_rate')
    def _compute_tax_withheld(self):
        for move in self:
            if not move.is_nodomicilied:
                move.tax_withheld = 0.00
                continue
            amount = move.neto_rent * move.retention_rate / 100.0
            currency = move.company_currency_id
            move.tax_withheld = currency.round(amount) if currency else round(amount, 2)

