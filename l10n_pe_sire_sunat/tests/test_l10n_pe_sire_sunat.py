from pytz import timezone
from datetime import datetime

from odoo.tests.common import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestL10nPeSireSunat(TransactionCase):

    def setUp(self):
        super().setUp()
        self.frozen_today = datetime(
            year=2024,
            month=5,
            day=30,
            hour=0,
            minute=0,
            second=0,
            tzinfo=timezone("utc"),
        )
        self.company = self.env.ref("base.main_company")
        self.company.write(
            {
                "vat": "20551583041",
                "country_id": self.env.ref("base.pe").id,
                "ple_type_contributor": "CUO",
            }
        )
        self.tax_group = self.env["account.tax.group"].create(
            {
                "name": "IGV",
                "l10n_pe_edi_code": "IGV",
            }
        )
        self.tax_18 = self.env["account.tax"].create(
            {
                "name": "tax_18",
                "amount_type": "percent",
                "amount": 18,
                "l10n_pe_edi_tax_code": "1000",
                "l10n_pe_edi_unece_category": "S",
                "type_tax_use": "sale",
                "tax_group_id": self.tax_group.id,
            }
        )
        self.product = self.env["product.product"].create(
            {
                "name": "product_ple",
                "uom_po_id": self.env.ref("uom.product_uom_kgm").id,
                "uom_id": self.env.ref("uom.product_uom_kgm").id,
                "lst_price": 1000.0,
            }
        )
        self.partner_a = self.env["res.partner"].search([("id", "=", 1)], limit=1)
        self.partner_a.write(
            {
                "vat": "20551583041",
                "l10n_latam_identification_type_id": self.env.ref("l10n_pe.it_RUC").id,
                "country_id": self.env.ref("base.pe").id,
            }
        )
        self.time_name = datetime.now().strftime("%H%M%S")
        self.currency_id = self.env["res.currency"].search(
            [("name", "=", "PEN")], limit=1
        )
        move_out_invoice = self.env["account.move"].create(
            {
                "name": "F C01-%s1" % self.time_name,
                "move_type": "out_invoice",
                "partner_id": self.partner_a.id,
                "invoice_date": "2024-05-30",
                "date": "2024-05-30",
                "currency_id": self.currency_id.id,
                "exchange_rate": 1.000000,
                "origin_l10n_latam_document_type_id": self.env.ref(
                    "l10n_pe.document_type01"
                ).id,
                "l10n_latam_document_type_id": self.env.ref(
                    "l10n_pe.document_type01"
                ).id,
                "invoice_line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": self.product.id,
                            "product_uom_id": self.env.ref("uom.product_uom_kgm").id,
                            "price_unit": 2000.0,
                            "quantity": 5,
                            "tax_ids": [(6, 0, self.tax_18.ids)],
                        },
                    )
                ],
            }
        )
        move_out_invoice.action_post()

    def test_l10n_pe_sire_sunat_action_generate_files(self):
        # sire sale
        sire_sale_report_id = self.env["sire.sale.wizard"].create(
            {
                "date_start": "2024-05-29",
                "date_end": "2024-05-31",
                "company_id": self.company.id,
                "state_send": "1",
                "opportunity_code": "02",
            }
        )
        sire_sale_report_id.action_generate_files()
        self.assertTrue(sire_sale_report_id.xlsx_binary)
        self.assertTrue(sire_sale_report_id.zip_binary)
