import base64
import re
import zipfile

from io import BytesIO

from odoo import models, fields, api
from odoo.exceptions import ValidationError

try:
    from odoo.tools.misc import xlsxwriter
except ImportError:
    import xlsxwriter

from ..reports.sire_purchase_not_domiciled_informed import SirePurchaseNotDomiciledInformedXlsx, SirePurchaseNotDomiciledInformedTxt
from ..reports.sire_purchase_not_domiciled_subsequent_adjustments import SirePurchaseNotDomiciledSubsequentAdjustmentsXlsx, SirePurchaseNotDomiciledSubsequentAdjustmentsTxt
from ..reports.sire_purchase_not_domiciled_general_format import SirePurchaseNotDomiciledGeneralFormatXlsx, SirePurchaseNotDomiciledGeneralFormatTxt

# Campo 10 RCE No Domiciliados: tipos de CP que sustentan el credito fiscal aceptados por SUNAT.
NODOM_SUSTENTO_ALLOWED_CODES = ('00', '46', '50', '51', '52', '53')
# Serie y numero: solo letras y numeros (SUNAT rechaza "/", espacios, etc.).
NODOM_ALLOWED_CHARS = re.compile(r'^[A-Za-z0-9]*$')
NODOM_MAX_LINES_DIALOG = 50


class SirePurchaseNotDomiciledWizard(models.TransientModel):
    _name = 'sire.purchase.not.domiciled.wizard'
    _inherit = 'sire.purchase.base'
    _description = 'Sire Purchase Not Domiciled Wizard'

    state_send = fields.Selection(
        selection=[
            ('0', '[0] Cierre de operaciones - Bajo de inscripciones en el RUC'),
            ('1', '[1] Empresa o entidad operativa'),
            ('2', '[2] Cierre de libro - No obligado a llevarlo')
        ],
        string='Estado de envío',
        required=True
    )
    opportunity_code = fields.Selection(
        selection=[
            ('00', '[00] RCE - No domiciliados informado'),
            ('03', '[03] RCE - Cuando realiza ajustes posteriores'),
            ('06', '[06] Reporte de ajustes posteriores de periodos anteriores al nuevo sistema de registros - Formato general'),
        ],
        string='Código de oportunidad',
        required=True
    )
    correlative = fields.Char(string='Correlativo')
    skip_nodom_validation = fields.Boolean(
        string='Generar aunque tenga observaciones',
        help='Si se marca, el TXT se genera aunque existan observaciones. '
             'La lista de observaciones se muestra igual como advertencia.'
    )

    @api.onchange('opportunity_code')
    def _onchange_opportunity_code(self):
        if self.correlative:
            self.correlative = ''

    def _select_sire_purchase(self):
        # Nombre del asiento sin limpiar, solo para mostrar en las observaciones.
        return super()._select_sire_purchase() + """,
            COALESCE(account_move.name, '') AS move_display_name
        """

    def _where_sire_purchase(self):
        return super()._where_sire_purchase() + """
            AND (
                account_move.is_nodomicilied = true
            )
        """

    def _generate_xlsx_file(self, processed_results):
        if self.opportunity_code == '00':
            xlsx_report = SirePurchaseNotDomiciledInformedXlsx(self, processed_results)
        elif self.opportunity_code == '03':
            xlsx_report = SirePurchaseNotDomiciledSubsequentAdjustmentsXlsx(self, processed_results)
        elif self.opportunity_code == '06':
            xlsx_report = SirePurchaseNotDomiciledGeneralFormatXlsx(self, processed_results)
        else:
            raise ValidationError('Por favor, se necesita un código de oportunidad para generar el reporte, gracias.')
        return {
            'xlsx_content': xlsx_report.get_content(),
            'xlsx_filename': xlsx_report.get_filename()
        }

    def _generate_txt_file(self, processed_results):
        if self.opportunity_code == '00':
            txt_report = SirePurchaseNotDomiciledInformedTxt(self, processed_results)
        elif self.opportunity_code == '03':
            txt_report = SirePurchaseNotDomiciledSubsequentAdjustmentsTxt(self, processed_results)
        elif self.opportunity_code == '06':
            txt_report = SirePurchaseNotDomiciledGeneralFormatTxt(self, processed_results)
        else:
            raise ValidationError('Por favor, se necesita un código de oportunidad para generar el reporte, gracias.')
        return {
            'txt_content': txt_report.get_content(),
            'txt_filename': txt_report.get_filename()
        }

    def _generate_zip_file(self, txt_filename, txt_content):
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr(txt_filename, txt_content.encode())
        zip_binary = base64.b64encode(zip_buffer.getvalue())
        zip_filename = '{}.zip'.format(txt_filename.split('.')[0])
        return {
            'zip_binary': zip_binary,
            'zip_filename': zip_filename
        }

    def _generate_files(self, processed_results=None):
        if processed_results is None:
            processed_results = self._process_query_results()
        xlsx_values = self._generate_xlsx_file(processed_results)
        txt_values = self._generate_txt_file(processed_results)
        zip_values = self._generate_zip_file(txt_values.get('txt_filename'), txt_values.get('txt_content', '\n'))
        return {
            'xlsx_values': xlsx_values,
            'txt_values': txt_values,
            'zip_values': zip_values
        }

    def _save_generate_files(self, file_values):
        has_content_values = file_values['txt_values'].get('txt_content', False)
        error_dialog = 'No hay contenido que presentar para este periodo.' if not has_content_values else ''
        self.write({
            'xlsx_binary': base64.b64encode(file_values['xlsx_values'].get('xlsx_content')),
            'xlsx_filename': file_values['xlsx_values'].get('xlsx_filename'),
            'zip_binary': file_values['zip_values'].get('zip_binary'),
            'zip_filename': file_values['zip_values'].get('zip_filename'),
            'error_dialog': error_dialog,
        })

    def _return_view_sire_purchase(self):
        wizard_form_id = self.env.ref('l10n_pe_sire_sunat.sire_purchase_not_domiciled_wizard_form_view').id
        return {
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sire.purchase.not.domiciled.wizard',
            'views': [(wizard_form_id, 'form')],
            'view_id': wizard_form_id,
            'res_id': self.id,
            'target': 'new'
        }

    # -------------------------------------------------------------------------
    # Validacion previa a la generacion del TXT (no modifica datos)
    # -------------------------------------------------------------------------

    @staticmethod
    def _nodom_split_ref(ref):
        """Misma regla que SirePurchaseNotDomiciledInformedTxt para los campos 5 y 6."""
        ref = (ref or '').strip()
        if '-' in ref:
            parts = ref.split('-')
            return parts[0].strip(), parts[1].strip().lstrip('0')
        return '', ref.lstrip('0')

    @staticmethod
    def _nodom_value(dict_result, key):
        value = dict_result.get(key)
        return str(value).strip() if value not in (None, False) else ''

    def _get_nodom_observations(self, processed_results):
        """Revisa los mismos valores que se escriben en el TXT. No modifica datos."""
        observations = []
        for dict_result in processed_results:
            get = lambda key: self._nodom_value(dict_result, key)
            base = {
                'invoice_name': get('move_display_name') or get('invoice_name'),
                'ref': get('ref'),
                'partner_name': get('partner_name'),
                'invoice_date': get('invoice_date'),
            }

            def add(field_number, field_label, value, message):
                observations.append(dict(
                    base,
                    field_number=field_number,
                    field_label=field_label,
                    value=value,
                    message=message,
                ))

            # Campos 5 y 6: serie y numero del comprobante (desde la referencia)
            ref_serie, ref_correlative = self._nodom_split_ref(dict_result.get('ref'))
            if not ref_correlative:
                add(6, 'Número del comprobante', base['ref'],
                    'La referencia de la factura está vacía.')
            elif not NODOM_ALLOWED_CHARS.match(ref_correlative):
                add(6, 'Número del comprobante', ref_correlative,
                    'Contiene caracteres no permitidos (solo letras y números). Corregir la referencia.')
            if ref_serie and not NODOM_ALLOWED_CHARS.match(ref_serie):
                add(5, 'Serie del comprobante', ref_serie,
                    'Contiene caracteres no permitidos (solo letras y números). Corregir la referencia.')

            # Campos 10 a 13: sustento del credito fiscal
            sustento_code = get('inv_type_document_code')
            inv_serie = get('inv_serie')
            inv_correlative = get('inv_correlative')
            if sustento_code and sustento_code not in NODOM_SUSTENTO_ALLOWED_CODES:
                add(10, 'Tipo CP que sustenta el crédito fiscal', sustento_code,
                    'Código no permitido. Valores aceptados: {}.'.format(
                        ', '.join(NODOM_SUSTENTO_ALLOWED_CODES)))
            if not sustento_code and (inv_serie or inv_correlative):
                add(10, 'Tipo CP que sustenta el crédito fiscal', '',
                    'Hay serie o número de sustento sin tipo de documento.')
            if inv_serie and not NODOM_ALLOWED_CHARS.match(inv_serie):
                add(11, 'Serie del sustento', inv_serie,
                    'Contiene caracteres no permitidos (solo letras y números).')
            if inv_correlative and not NODOM_ALLOWED_CHARS.match(inv_correlative):
                add(13, 'Número del sustento', inv_correlative,
                    'Contiene caracteres no permitidos (solo letras y números).')

            # Campos obligatorios
            if not get('country_code'):
                add(17, 'País de residencia', '',
                    'El proveedor no tiene país o el país no tiene código SUNAT.')
            if not get('partner_vat'):
                add(20, 'Identificación del sujeto no domiciliado', '',
                    'El proveedor no tiene número de identificación.')
            if not get('cdi'):
                add(30, 'Convenio para evitar la doble imposición', '',
                    'Completar CDI en la pestaña No Domiciliado (00 si no hay convenio).')
            if not get('type_rent_code'):
                add(32, 'Tipo de renta', '',
                    'Completar Tipo de Renta en la factura.')
        return observations

    def _get_nodom_observations_text(self, observations, blocking=True):
        header = (
            'No se generó el TXT: hay {} observación(es) que SUNAT rechazaría. '
            'Corrija los datos en las facturas o socios (ver Excel de observaciones).'
            if blocking else
            'TXT generado con {} observación(es) que SUNAT podría rechazar.'
        ).format(len(observations))
        lines = [header, '']
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
        worksheet = workbook.add_worksheet('Observaciones')
        style_header = workbook.add_format({'bold': True, 'size': 10, 'text_wrap': True, 'valign': 'vcenter'})
        style_content = workbook.add_format({'size': 10})
        headers = ['N°', 'Asiento', 'Referencia', 'Proveedor', 'Fecha de emisión',
                   'Campo TXT', 'Dato', 'Valor actual', 'Observación']
        widths = [5, 22, 22, 40, 14, 10, 40, 22, 70]
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

    def _save_nodom_observations(self, observations):
        self.write({
            'xlsx_binary': base64.b64encode(self._generate_nodom_observations_xlsx(observations)),
            'xlsx_filename': 'Observaciones RCE no domiciliados {} {}{}.xlsx'.format(
                self.company_id.name, self.year, self.month),
            'zip_binary': False,
            'zip_filename': '',
            'error_dialog': self._get_nodom_observations_text(observations, blocking=True),
        })

    def action_generate_files(self):
        self.write({
            'xlsx_binary': False,
            'xlsx_filename': '',
            'zip_binary': False,
            'zip_filename': '',
            'error_dialog': '',
        })
        processed_results = self._process_query_results()
        observations = self._get_nodom_observations(processed_results)
        if observations and not self.skip_nodom_validation:
            self._save_nodom_observations(observations)
            return self._return_view_sire_purchase()

        file_values = self._generate_files(processed_results)
        self._save_generate_files(file_values)
        if observations:
            self.error_dialog = '\n\n'.join(filter(None, [
                self._get_nodom_observations_text(observations, blocking=False),
                self.error_dialog,
            ]))
        return self._return_view_sire_purchase()
