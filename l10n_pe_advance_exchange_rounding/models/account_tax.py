from odoo import api, models


class AccountTax(models.Model):
    _inherit = 'account.tax'

    @api.model
    def _add_tax_details_in_base_line(self, base_line, company, rounding_method=None):
        """Facturas con anticipo y redondeo de impuestos por línea: el IGV del
        documento se calcula sobre la base neta (suma de las bases ya redondeadas
        por línea) y se redondea una sola vez.

        Con el redondeo por línea, cada línea redondea su IGV y la suma de esos
        IGV difiere en céntimos del IGV del anticipo (redondeado en una sola
        línea): una factura saldada al 100 % con el anticipo quedaba con IGV y
        total 0.01-0.04 (F001-00001507 de EQUIPAMIENTO). Aquí el IGV en bruto de
        cada línea es su base redondeada por la tasa, sin redondear; el reparto
        nativo de la diferencia de redondeo (_round_tax_details_tax_amounts)
        deja el total en round(tasa x base neta). Las bases y el precio total de
        cada línea no cambian."""
        super()._add_tax_details_in_base_line(base_line, company, rounding_method=rounding_method)
        if (rounding_method or company.tax_calculation_rounding_method) != 'round_per_line':
            return
        if not self._l10n_pe_is_advance_invoice_base_line(base_line):
            return
        taxes_data = base_line['tax_details']['taxes_data']
        # Solo impuestos porcentuales no incluidos en el precio y, si hay varios,
        # sin uno que afecte la base del siguiente (p.ej. IGV + ICBPER se deja
        # como está).
        if not taxes_data or any(
            tax_data['tax'].amount_type != 'percent' or tax_data['price_include'] for tax_data in taxes_data
        ) or (len(taxes_data) > 1 and any(tax_data['tax'].include_base_amount for tax_data in taxes_data)):
            return
        rate = base_line['rate']
        for tax_data in taxes_data:
            factor = tax_data['tax'].amount / 100.0
            tax_data['raw_tax_amount_currency'] = tax_data['raw_base_amount_currency'] * factor
            tax_data['raw_tax_amount'] = tax_data['raw_base_amount_currency'] * factor / rate if rate else 0.0

    @api.model
    def _l10n_pe_is_advance_invoice_base_line(self, base_line):
        """Línea de una factura que aplica un anticipo (producto marcado como
        anticipo en alguna de sus líneas)."""
        record = base_line.get('record')
        if not isinstance(record, models.BaseModel) or record._name != 'account.move.line':
            return False
        move = record.move_id
        return move.is_invoice(include_receipts=True) and any(
            line.product_id.l10n_pe_advance for line in move.invoice_line_ids
        )
