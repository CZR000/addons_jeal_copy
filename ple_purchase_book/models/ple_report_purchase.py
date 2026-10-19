import ast
import base64
import re

from odoo.exceptions import ValidationError
from odoo import fields, models
from odoo.tools.misc import xlsxwriter
from io import BytesIO
from ..reports.purchase_report_excel import PurchaseReportExcel, PurchaseReportTxt

# Formato 8.2: tipos de CP que sustentan el credito fiscal aceptados por SUNAT.
NODOM_SUSTENTO_ALLOWED_CODES = ('00', '46', '50', '51', '52', '53')
# Serie y numero: solo letras y numeros (SUNAT rechaza "/", espacios, etc.).
NODOM_ALLOWED_CHARS = re.compile(r'^[A-Za-z0-9]*$')
NODOM_MAX_LINES_DIALOG = 50


class PleReportPurchase(models.Model):
    _name = 'ple.report.purchase'
    _description = 'PLE Report Purchase Record'
    _inherit = 'ple.report.base'

    move_ids = fields.Many2many(
        comodel_name='account.move',
        string='factura relacionadas'
    )

    xls_filename_8_1 = fields.Char()
    xls_binary_8_1 = fields.Binary(
        string='Reporte Excel - 8.1'
    )
    txt_filename_8_1 = fields.Char()
    txt_binary_8_1 = fields.Binary(
        string='Reporte TXT - 8.1'
    )
    xls_filename_8_2 = fields.Char()
    xls_binary_8_2 = fields.Binary(
        string='Reporte Excel - 8.2'
    )
    txt_filename_8_2 = fields.Char()
    txt_binary_8_2 = fields.Binary(
        string='Reporte TXT - 8.2')

    error_dialog_8_2 = fields.Text(readonly=True)

    def action_generate_excel(self):
        query = """
            SELECT
            TO_CHAR(am.date, 'YYYYMM00') AS period,
            replace(replace(replace(am.name, '/', ''), '-', ''), ' ', '') AS number_origin,
            (SELECT
                CASE
                    WHEN company.ple_type_contributor = 'CUO' THEN
                        (SELECT COALESCE(ple_correlative, 'M000000001') FROM account_move_line where move_id = am.id LIMIT 1)
                    WHEN company.ple_type_contributor = 'RER' THEN 'M-RER'
                    ELSE ''
                END
            ) AS journal_correlative,
            TO_CHAR(am.invoice_date, 'DD/MM/YYYY') AS date_invoice,
            CASE WHEN document_type.code is not null AND document_type.code = '14' AND am.state != 'cancel' THEN
                TO_CHAR(am.invoice_date_due, 'DD/MM/YYYY') ELSE ''
            END AS date_due,
            COALESCE(document_type.code, '') AS voucher_sunat_code,
            COALESCE(split_part(replace(am.ref, ' ', ''), '-', 1), '0000') AS voucher_series,
            COALESCE(am.year_aduana, '') AS year_aduana,
            split_part(replace(am.ref, ' ', ''), '-', 2) AS correlative,
            COALESCE(identification_type.l10n_pe_vat_code, '') AS customer_document_type,
            COALESCE(partner.vat, '') AS customer_document_number,
            validate_string(partner.name, 99) AS customer_name,
            get_tax_purchase(am.id, am.move_type) AS tax_data,
            currency.name AS code_currency,
            COALESCE(ROUND(am.exchange_rate, 3),'0.00')AS currency_rate,
            COALESCE(TO_CHAR(am.origin_invoice_date, 'DD/MM/YYYY'), '') AS origin_date_invoice,
            COALESCE(origin_document_type.code, '') AS origin_document_code,
            split_part(replace(COALESCE(am.origin_number, ''), ' ', ''), '-', 1) AS origin_serie,
            split_part(replace(COALESCE(am.origin_number, ''), ' ', ''), '-', 2) AS origin_correlative,
            COALESCE(am.ple_state, '') AS ple_state,
            COALESCE(type_services.code, '') AS class_good_services,
            am.id AS invoice_id,
            {ple_report_purchase_id} AS ple_report_purchase_id, 
            COALESCE(am.is_nodomicilied, 'False') AS is_nodomicilied,
            COALESCE(am.igv_withholding_indicator, 'False') AS retention,
            CASE WHEN am.bool_pay_invoice THEN '1' ELSE ' ' END AS type_pay,
            COALESCE(code_aduana.code, '') AS sunat_origin_code,
            COALESCE(am.voucher_number, '') AS voucher_number,
            COALESCE(TO_CHAR(am.voucher_payment_date, 'DD/MM/YYYY'), '') AS voucher_payment_date,
            COALESCE(l10n_latam_document_type.code, '') AS l10n_latam_document_type,     
            COALESCE(am.inv_serie, '') AS inv_serie,
            COALESCE(am.inv_year_dua_dsi, '') AS inv_year_dua_dsi,
            COALESCE(CAST(TO_CHAR(am.inv_retention_igv, '9999999999D99')AS DECIMAL(9,2)), '0.00') AS inv_retention_igv,
            COALESCE(am.inv_correlative, '') AS inv_correlative,
            COALESCE(TO_CHAR(am.hard_rent, '9999999999D99') , '') AS hard_rent,
            COALESCE(TO_CHAR(am.deduccion_cost, '9999999999D99'), '') AS deduccion_cost,
            COALESCE(TO_CHAR(am.neto_rent, '9999999999D99'), '') AS neto_rent,
            COALESCE(TO_CHAR(am.retention_rate, '999D99'), '') AS retention_rate,
            COALESCE(TO_CHAR(am.tax_withheld, '9999999999D99'), '') AS tax_withheld,
            COALESCE(am.cdi, '') AS cdi,
            COALESCE(am.application_article, '') AS application_article,
            COALESCE(link_economic.code, '') AS linkage_code,
            COALESCE(TO_CHAR(exoneration_nodomicilied.code, '99999999'), '') AS exoneration_nodomicilied_code,
            COALESCE(type_rent.code, '') AS type_rent_code,
            COALESCE(service_taken.code, '') AS taken_code,
            COALESCE(country.l10n_pe_sunat_code, '') AS country_code,
            COALESCE(country.name) AS country_name,
            COALESCE(state.name, '') AS state_name,
            COALESCE(partner.city, '') AS city,
            COALESCE(partner.street, '') AS street,
            COALESCE(partner.street2, '') AS street2
            -- QUERIES TO MATCH MULTI TABLES
            FROM account_move am
            --  TYPE JOIN |  TABLE                         | VARIABLE                    | MATCH
            --  https://www.sqlshack.com/sql-multiple-joins-for-beginners-with-examples/
                INNER JOIN  "res_partner"                    partner                       ON  am.partner_id = partner.id
                INNER JOIN  "res_company"                    company                       ON  am.company_id = company.id
                INNER JOIN  "res_currency"                   currency                      ON  am.currency_id = currency.id
                LEFT JOIN   "l10n_latam_document_type"       origin_document_type          ON am.origin_l10n_latam_document_type_id = origin_document_type.id
                LEFT JOIN   "l10n_latam_document_type"       document_type                 ON am.l10n_latam_document_type_id = document_type.id
                LEFT JOIN   "l10n_latam_identification_type" identification_type           ON partner.l10n_latam_identification_type_id = identification_type.id
                LEFT JOIN   "res_country"                    country                       ON partner.country_id = country.id
                LEFT JOIN   "res_country_state"              state                         ON partner.state_id = state.id        
                LEFT JOIN   "account_spot_retention"         account_spot_retention        ON am.retention_id = account_spot_retention.id    
                LEFT JOIN   "link_economic"                  link_economic                 ON am.linkage_id = link_economic.id
                LEFT JOIN   "exoneration_nodomicilied"       exoneration_nodomicilied      ON am.exoneration_nodomicilied_id = exoneration_nodomicilied.id
                LEFT JOIN   "type_rent"                      type_rent                     ON am.type_rent_id = type_rent.id
                LEFT JOIN   "service_taken"                  service_taken                 ON am.taken_id = service_taken.id
                LEFT JOIN   "code_aduana"                    code_aduana                   ON am.code_aduana = code_aduana.id
                LEFT JOIN   "l10n_latam_document_type"       l10n_latam_document_type      ON am.inv_type_document = l10n_latam_document_type.id
                LEFT JOIN   "classification_services"        type_services                 ON am.types_goods_services_id = type_services.id
            WHERE
            -- FILTER QUERIES
            ((((((((am."company_id" = {company_id}) AND
                    (am."move_type" in ('{move_type1}','{move_type2}'))) AND
                    (am."ple_date" >= '{date_start}')) AND
                    (am."ple_date" <= '{date_end}')) AND
                    ((am."state" not in ('{state_1}','{state_2}')) OR am."state" IS NULL)) AND
                    (am."journal_id" in (SELECT "account_journal".id FROM "account_journal" WHERE
                                                    ("account_journal"."ple_no_include" IS NULL or "account_journal"."ple_no_include" = false ) AND
                                                    ("account_journal"."company_id" IS NULL  OR ("account_journal"."company_id" in ({company_id})))
                                                    ORDER BY  "account_journal"."id"  ))) AND
                    (am."journal_id" in (SELECT "account_journal".id FROM "account_journal" WHERE ("account_journal"."type" = '{journal_type}') AND
                                                    ("account_journal"."company_id" IS NULL  OR ("account_journal"."company_id" in ({company_id})))
                                                    ORDER BY  "account_journal"."id"  ))) AND
                    (am."ple_its_declared" IS NULL or am."ple_its_declared" = false )) AND
                    (am."company_id" IS NULL  OR (am."company_id" in ({company_id})))
            -- ORDER DATA
            ORDER BY  am."date" DESC,am."name" DESC,am."id" DESC
                """.format(
            company_id=self.company_id.id,
            move_type1='in_invoice',
            move_type2='in_refund',
            date_start=self.date_start,
            date_end=self.date_end,
            state_1='draft',
            state_2='cancel',
            journal_type='purchase',
            ple_report_purchase_id=self.id
        )
                
        try:
            self.env.cr.execute(query)
            query_data = self.env.cr.dictfetchall()
            self.get_excel_data(query_data)
        except Exception as error:
            raise ValidationError(f'Error al ejecutar la query, comunicarse con el administrador: \n {error}')

    def get_excel_data(self, data_lines):
        list_data = []
        invoices = []
        for obj_line in data_lines:
            tax_data = ast.literal_eval(obj_line['tax_data'])
            obj_line.update({
                'P_BASE_GDG': tax_data[0],
                'P_TAX_GDG': tax_data[1],
                'P_BASE_GDM': tax_data[2],
                'P_TAX_GDM': tax_data[3],
                'P_BASE_GDNG': tax_data[4],
                'P_TAX_GDNG': tax_data[5],
                'P_BASE_NG': tax_data[6],
                'P_TAX_ISC': tax_data[7],
                'P_TAX_ICBP': tax_data[8],
                'P_TAX_OTHER': tax_data[9],
                'AMOUNT_TOTAL': tax_data[10],
            })
            country_name = obj_line.get('country_name')
            if isinstance(country_name, dict):
                ultima_clave = list(country_name.keys())[-1]
                new_country_name = country_name[ultima_clave]
            else:
                new_country_name = country_name or ''
            value = {
                'period': obj_line.get('period', ''),
                'number_origin': obj_line.get('number_origin', ''),
                'journal_correlative': obj_line.get('journal_correlative', ''),
                'date_invoice': obj_line.get('date_invoice', ''),
                'date_due': obj_line.get('date_due', ''),
                'voucher_sunat_code': obj_line.get('voucher_sunat_code', ''),
                'voucher_series': obj_line.get('voucher_series', ''),
                'voucher_year_dua_dsi': obj_line.get('year_aduana', ''),
                'correlative': obj_line.get('correlative', ''),
                'customer_document_type': obj_line.get('customer_document_type', ''),
                'customer_document_number': obj_line.get('customer_document_number', ''),
                'customer_name': obj_line.get('customer_name', ''),
                'base_gdg': obj_line.get('P_BASE_GDG', ''),
                'tax_gdg': obj_line.get('P_TAX_GDG', ''),
                'tax_icbp': obj_line.get('P_TAX_ICBP', ''),
                'base_gdm': obj_line.get('P_BASE_GDM', ''),
                'tax_gdm': obj_line.get('P_TAX_GDM', ''),
                'base_gdng': obj_line.get('P_BASE_GDNG', ''),
                'tax_gdng': obj_line.get('P_TAX_GDNG', ''),
                'amount_untaxed': obj_line.get('P_BASE_NG', ''),
                'isc': obj_line.get('P_TAX_ISC', ''),
                'another_taxes': obj_line.get('P_TAX_OTHER', ''),
                'amount_total': float(obj_line.get('P_BASE_GDG', '')) + float(obj_line.get('P_TAX_GDG', '')) + float(obj_line.get('P_TAX_ICBP', '')) + float(
                    obj_line.get('P_BASE_GDM', '')) + float(obj_line.get('P_TAX_GDM', '')) + float(obj_line.get('P_BASE_GDNG', '')) + float(
                    obj_line.get('P_TAX_GDNG', '')) + float(obj_line.get('P_BASE_NG', '')) + float(obj_line.get('P_TAX_OTHER', '')),
                'code_currency': obj_line.get('code_currency', ''),
                'currency_rate': obj_line.get('currency_rate', ''),
                'origin_date_invoice': obj_line.get('origin_date_invoice', ''),
                'origin_document_code': obj_line.get('origin_document_code', ''),
                'origin_serie': obj_line.get('origin_serie', ''),
                'origin_code_aduana': obj_line.get('sunat_origin_code', ''),
                'origin_correlative': obj_line.get('origin_correlative', ''),
                'voucher_date': obj_line.get('voucher_payment_date', ''),
                'voucher_number': obj_line.get('voucher_number', ''),
                'retention': '1' if obj_line.get('retention', '') else ' ',
                'type_pay_invoice': obj_line.get('type_pay', ''),
                'ple_state': obj_line.get('ple_state', ''),
                'class_good_services': obj_line.get('class_good_services', ''),
                'irregular_societies': obj_line.get('irregular_societies', ''),
                'error_exchange_rate': obj_line.get('error_exchange_rate', ''),
                'supplier_not_found': obj_line.get('supplier_not_found', ''),
                'suppliers_resigned': obj_line.get('suppliers_resigned', ''),
                'dni_ruc': obj_line.get('dni_ruc', ''),
                'l10n_latam_document_type': obj_line.get('l10n_latam_document_type', ''),
                'inv_serie': obj_line.get('inv_serie', ''),
                'inv_year_dua_dsi': obj_line.get('inv_year_dua_dsi', ''),
                'inv_correlative': obj_line.get('inv_correlative', ''),
                'inv_retention_igv': obj_line.get('inv_retention_igv', '0.00'),
                'country_code': obj_line.get('country_code', ''),
                'partner_street': "{} {} {} {} {}".format(new_country_name,
                                                          obj_line.get('state_name', ''), obj_line.get('city', ''),
                                                          obj_line.get('street', ''),
                                                          obj_line.get('street2', '')).strip(),
                'linkage_code': obj_line.get('linkage_code', ''),
                'hard_rent': self.get_values_error(obj_line.get('hard_rent', '')),
                'deduccion_cost': self.get_values_error(obj_line.get('deduccion_cost', '')),
                'rent_neta': self.get_values_error(obj_line.get('neto_rent', '')),
                'retention_rate': self.get_values_error(obj_line.get('retention_rate', '')),
                'tax_withheld': self.get_values_error(obj_line.get('tax_withheld', '')),
                'cdi': obj_line.get('cdi', ''),
                'exoneration_nodomicilied_code': obj_line.get('exoneration_nodomicilied_code', ''),
                'type_rent_code': obj_line.get('type_rent_code', ''),
                'taken_code': obj_line.get('taken_code', ''),
                'application_article': obj_line.get('application_article', ''),
                'partner_nodomicilied': obj_line.get('is_nodomicilied', ''),
                'invoice_id': obj_line.get('invoice_id'),
            }
            # Formato 8.2: si la referencia no tiene guion, el numero completo va
            # al campo 7 (numero) y la serie queda vacia.
            if self._is_line_8_2(value) and not value['correlative'] and value['voucher_series']:
                value.update({
                    'correlative': value['voucher_series'],
                    'voucher_series': '',
                })
            if value.get('origin_document_code') != '50':
                value_update = {'origin_code_aduana': ''}
                value.update(value_update)
            else:
                value_update = {'origin_code_aduana': obj_line.get('origin_serie', '')}
                value.update(value_update)

            list_data.append(value)
            invoices.append(obj_line['invoice_id'])

        # Validacion previa del formato 8.2 (No Domiciliados). No modifica datos.
        observations = self._get_nodom_observations_8_2(list_data)
        if observations:
            # El 8.2 no se genera y sus facturas no quedan asociadas al reporte,
            # para que "Declarar a SUNAT" no las marque como declaradas.
            nodom_ids = {value['invoice_id'] for value in list_data if self._is_line_8_2(value)}
            invoices = [invoice_id for invoice_id in invoices if invoice_id not in nodom_ids]
            list_data = [value for value in list_data if not self._is_line_8_2(value)]

        purchase_report = PurchaseReportTxt(self, list_data)
        values_content = purchase_report.get_content()
        values_content2 = purchase_report.get_content8_2()

        purchase_report_xls = PurchaseReportExcel(self, list_data)
        values_content_xls = purchase_report_xls.get_content()
        value_content_xls_8_2 = purchase_report_xls.get_content('2')

        values = {
            'txt_binary_8_1': base64.b64encode(values_content.encode() or '\n'.encode()),
            'txt_filename_8_1': purchase_report.get_filename(),
            'error_dialog': 'No hay contenido para presentar en el registro de ventas electrónicos de este periodo.' if not values_content else '',
            'xls_binary_8_1': base64.b64encode(values_content_xls),
            'xls_filename_8_1': purchase_report_xls.get_filename(),
            'txt_binary_8_2': base64.b64encode(values_content2.encode() or '\n'.encode()),
            'txt_filename_8_2': purchase_report.get_filename2(),
            'error_dialog_8_2': 'No hay contenido para presentar en el registro de ventas electrónicos de este periodo.' if not values_content2 else '',
            'xls_binary_8_2': base64.b64encode(value_content_xls_8_2),
            'xls_filename_8_2': purchase_report_xls.get_filename('2'),
            'date_ple': fields.Date.today(),
            'state': 'load',
            'move_ids': invoices
        }
        if observations:
            values.update({
                'txt_binary_8_2': False,
                'txt_filename_8_2': False,
                'xls_binary_8_2': base64.b64encode(self._generate_nodom_observations_xlsx(observations)),
                'xls_filename_8_2': 'Observaciones_compras_8.2.xlsx',
                'error_dialog_8_2': self._get_nodom_observations_text(observations),
            })
        self.write(values)

    def action_close(self):
        super(PleReportPurchase, self).action_close()
        for move in self.move_ids:
            move.write({'ple_its_declared': True})

    def action_rollback(self):
        super(PleReportPurchase, self).action_rollback()
        for move in self.move_ids:
            move.write({'ple_its_declared': False})
        self.write({
            'txt_binary_8_1': False,
            'txt_filename_8_1': False,
            'xls_binary_8_1': False,
            'xls_filename_8_1': False,
            'txt_binary_8_2': False,
            'txt_filename_8_2': False,
            'xls_binary_8_2': False,
            'xls_filename_8_2': False,
            'error_dialog_8_2': False,
            'move_ids': False
        })

    def get_values_error(self, valor):
        result = ''
        data = valor.strip()
        if data == '.00':
            result = '0.00'
        else:
            result = valor

        return result

    # -------------------------------------------------------------------------
    # Validacion previa del formato 8.2 (No Domiciliados)
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_line_8_2(value):
        """Misma condicion que usa PurchaseReportTxt.get_content8_2."""
        return value['voucher_sunat_code'] in ['91', '97', '98'] and value['partner_nodomicilied'] != ''

    @staticmethod
    def _nodom_text(value):
        return str(value).strip() if value not in (None, False) else ''

    def _get_nodom_observations_8_2(self, list_data):
        """Revisa los mismos valores que se escriben en el TXT 8.2."""
        observations = []
        moves = self.env['account.move'].browse(
            [value['invoice_id'] for value in list_data if self._is_line_8_2(value)]
        )
        move_by_id = {move.id: move for move in moves}
        for value in list_data:
            if not self._is_line_8_2(value):
                continue
            get = lambda key: self._nodom_text(value.get(key))
            move = move_by_id.get(value['invoice_id'])
            base = {
                'invoice_name': move.name if move else get('number_origin'),
                'ref': (move.ref or '') if move else '',
                'partner_name': get('customer_name'),
                'invoice_date': get('date_invoice'),
            }

            def add(field_number, field_label, current, message):
                observations.append(dict(
                    base,
                    field_number=field_number,
                    field_label=field_label,
                    value=current,
                    message=message,
                ))

            # Campos 6 y 7: serie y numero del comprobante (desde la referencia)
            voucher_series = get('voucher_series')
            correlative = get('correlative')
            if not correlative:
                add(7, 'Número del comprobante', '', 'La referencia de la factura está vacía.')
            elif not NODOM_ALLOWED_CHARS.match(correlative):
                add(7, 'Número del comprobante', correlative,
                    'Contiene caracteres no permitidos (solo letras y números). Corregir la referencia.')
            if voucher_series and not NODOM_ALLOWED_CHARS.match(voucher_series):
                add(6, 'Serie del comprobante', voucher_series,
                    'Contiene caracteres no permitidos (solo letras y números). Corregir la referencia.')

            # Campos 11 a 14: sustento del credito fiscal
            sustento_code = get('l10n_latam_document_type')
            if sustento_code == '0':
                sustento_code = ''
            inv_serie = get('inv_serie')
            inv_correlative = get('inv_correlative')
            if sustento_code and sustento_code not in NODOM_SUSTENTO_ALLOWED_CODES:
                add(11, 'Tipo CP que sustenta el crédito fiscal', sustento_code,
                    'Código no permitido. Valores aceptados: {}.'.format(', '.join(NODOM_SUSTENTO_ALLOWED_CODES)))
            if not sustento_code and (inv_serie or inv_correlative):
                add(11, 'Tipo CP que sustenta el crédito fiscal', '',
                    'Hay serie o número de sustento sin tipo de documento.')
            if inv_serie and not NODOM_ALLOWED_CHARS.match(inv_serie):
                add(12, 'Serie del sustento', inv_serie,
                    'Contiene caracteres no permitidos (solo letras y números).')
            if inv_correlative and not NODOM_ALLOWED_CHARS.match(inv_correlative):
                add(14, 'Número del sustento', inv_correlative,
                    'Contiene caracteres no permitidos (solo letras y números).')

            # Campos obligatorios
            if not get('country_code'):
                add(18, 'País de residencia', '',
                    'El proveedor no tiene país o el país no tiene código SUNAT.')
            if not get('customer_document_number'):
                add(21, 'Identificación del sujeto no domiciliado', '',
                    'El proveedor no tiene número de identificación.')
            if not get('cdi'):
                add(31, 'Convenio para evitar la doble imposición', '',
                    'Completar CDI en la pestaña No Domiciliado (00 si no hay convenio).')
            if not get('type_rent_code'):
                add(33, 'Tipo de renta', '',
                    'Completar Tipo de Renta en la factura.')
        return observations

    def _get_nodom_observations_text(self, observations):
        lines = [
            'No se generó el TXT 8.2: hay {} observación(es) que SUNAT rechazaría. '
            'Corrija los datos en las facturas o socios (ver Excel de observaciones).'.format(len(observations)),
            '',
        ]
        for obs in observations[:NODOM_MAX_LINES_DIALOG]:
            lines.append('- {} | Ref. {} | {} | Campo {} ({}): {}'.format(
                obs['invoice_name'], obs['ref'] or '-', obs['partner_name'],
                obs['field_number'], obs['field_label'], obs['message']))
        if len(observations) > NODOM_MAX_LINES_DIALOG:
            lines.append('... y {} más.'.format(len(observations) - NODOM_MAX_LINES_DIALOG))
        return '\n'.join(lines)

    def _generate_nodom_observations_xlsx(self, observations):
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        worksheet = workbook.add_worksheet('Observaciones 8.2')
        style_header = workbook.add_format({'bold': True, 'size': 10, 'text_wrap': True, 'valign': 'vcenter'})
        style_content = workbook.add_format({'size': 10})
        headers = ['N°', 'Asiento', 'Referencia', 'Proveedor', 'Fecha de emisión',
                   'Campo TXT 8.2', 'Dato', 'Valor actual', 'Observación']
        widths = [5, 22, 22, 40, 14, 12, 40, 22, 70]
        for col, (title, width) in enumerate(zip(headers, widths)):
            worksheet.write(0, col, title, style_header)
            worksheet.set_column(col, col, width)
        for row, obs in enumerate(observations, start=1):
            values = [row, obs['invoice_name'], obs['ref'], obs['partner_name'], obs['invoice_date'],
                      obs['field_number'], obs['field_label'], obs['value'], obs['message']]
            for col, value in enumerate(values):
                worksheet.write(row, col, value, style_content)
        worksheet.autofilter(0, 0, len(observations), len(headers) - 1)
        worksheet.freeze_panes(1, 0)
        workbook.close()
        output.seek(0)
        return output.read()
