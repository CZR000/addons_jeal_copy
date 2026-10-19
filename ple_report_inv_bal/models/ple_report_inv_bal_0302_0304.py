import logging
from datetime import date

from odoo import models, _
from odoo.osv import expression

from ..reports.report_inv_bal_32 import InvBal32ReportExcel
from ..reports.report_inv_bal_partner import (
    InvBal33ReportExcel,
    InvBal34ReportExcel,
)

_logger = logging.getLogger(__name__)


class PleReportInvBalBook0302To0304(models.Model):
    """Formatos 3.2, 3.3 y 3.4 del Libro de Inventarios y Balances."""

    _inherit = 'ple.report.inv.bal.book'

    # ------------------------------------------------------------------
    # Acciones
    # ------------------------------------------------------------------
    def action_generate_02(self):
        """Formato 3.2 - Detalle de la cuenta 10 (Efectivo)."""
        return self._generate_single('02')

    def _prepare_report_02(self):
        self.ensure_one()
        report = InvBal32ReportExcel(self, self._get_data_32())
        return report

    def action_generate_03(self):
        """Formato 3.3 - Detalle de la cuenta 12 (Clientes)."""
        return self._generate_single('03')

    def _prepare_report_03(self):
        self.ensure_one()
        data = self._get_open_items(['12'], date_source='invoice')
        report = InvBal33ReportExcel(self, data)
        return report

    def action_generate_04(self):
        """Formato 3.4 - Detalle de la cuenta 14 (Personal y accionistas)."""
        return self._generate_single('04')

    def _prepare_report_04(self):
        self.ensure_one()
        data = self._get_open_items(['14'], date_source='move')
        report = InvBal34ReportExcel(self, data)
        return report

    # ------------------------------------------------------------------
    # Helpers compartidos
    # ------------------------------------------------------------------
    def _get_accounts_by_prefix(self, prefixes):
        """Cuentas de la compania cuyo codigo empieza con alguno de los
        prefijos dados, ordenadas por codigo."""
        self.ensure_one()
        domain = expression.AND([
            expression.OR([[('code', '=like', '%s%%' % p)] for p in prefixes]),
            [('company_ids', 'in', self.company_id.id)],
        ])
        accounts = self.env['account.account'].with_company(
            self.company_id
        ).search(domain)
        return accounts.sorted(lambda a: a.code or '')

    # ------------------------------------------------------------------
    # DATA - Formato 3.2 (cuenta 10)
    # ------------------------------------------------------------------
    def _get_data_32(self):
        """Saldo final de cada cuenta divisionaria de la 10 al `date_end`,
        con su entidad financiera (Tabla 3), numero de cuenta y moneda
        (Tabla 4) tomados del diario de banco/caja asociado."""
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(['10'])
        if not accounts:
            return {'lines': [], 'total_debit': 0.0, 'total_credit': 0.0}

        balances = self._balances_by_account(self.date_end, accounts.ids)

        journals = self.env['account.journal'].with_company(
            self.company_id
        ).search([
            ('company_id', '=', self.company_id.id),
            ('type', 'in', ('bank', 'cash')),
            ('default_account_id', 'in', accounts.ids),
        ])
        journal_by_account = {}
        for journal in journals:
            journal_by_account.setdefault(journal.default_account_id.id, journal)

        company_currency = self.company_id.currency_id
        lines = []
        total_debit = total_credit = 0.0
        for account in accounts:
            balance = balances.get(account.id, 0.0)
            if abs(balance) < 0.005:
                continue

            journal = journal_by_account.get(account.id)
            bank_account = journal.bank_account_id if journal else False
            bank = bank_account.bank_id if bank_account else False
            bank_code = (
                getattr(bank, 'sunat_bank_code', False)
                or getattr(bank, 'l10n_pe_edi_code', False)
                or '99'
            ) if bank else '99'
            currency = (
                (journal.currency_id if journal else False)
                or account.currency_id
                or company_currency
            )

            debit = balance if balance > 0 else 0.0
            credit = -balance if balance < 0 else 0.0
            total_debit += debit
            total_credit += credit
            lines.append({
                'code': account.code or '',
                'name': account.name or '',
                'bank_code': bank_code,
                'account_number': (bank_account.acc_number if bank_account else '') or '-',
                'currency': currency.name or '',
                'debit': debit,
                'credit': credit,
            })

        return {
            'lines': lines,
            'total_debit': total_debit,
            'total_credit': total_credit,
        }

    # ------------------------------------------------------------------
    # DATA - Formatos 3.3 / 3.4 (documentos pendientes por tercero)
    # ------------------------------------------------------------------
    def _get_open_items(self, prefixes, date_source='move', split_no_partner=False):
        """Documentos pendientes al `date_end` en las cuentas indicadas.

        El saldo pendiente de cada linea se calcula A LA FECHA DE CORTE:
        saldo de la linea menos las conciliaciones cuya `max_date` sea
        <= date_end. No se consideran los asientos de cierre de la fecha fin
        (ver _get_excluded_move_ids). Una conciliacion solo se descuenta si la linea
        contraria TAMBIEN cuenta: asiento publicado, fecha <= date_end y
        misma familia de cuentas. Asi el total del reporte siempre es igual
        al saldo contable de las cuentas, aunque existan conciliaciones
        contra asientos cancelados (p.ej. aperturas/cierres anulados).

        Agrupa por tercero (partner comercial) y documento (asiento). Las
        lineas sin tercero (p.ej. diferencias de cambio) se agrupan en una
        sola fila "VARIOS", o por asiento si `split_no_partner` es True.

        date_source:
            'invoice' -> fecha de emision del comprobante (invoice_date)
            'move'    -> fecha del asiento (inicio de la operacion)

        Retorna {'lines': [{doc_type, doc_number, name, doc_ref, amount,
        date}], 'total': float}.
        """
        self.ensure_one()
        accounts = self._get_accounts_by_prefix(prefixes)
        if not accounts:
            return {'lines': [], 'total': 0.0}

        self.env.cr.execute("""
            SELECT aml.id,
                   aml.balance
                   - COALESCE((SELECT SUM(p.amount)
                                 FROM account_partial_reconcile p
                                 JOIN account_move_line cl ON cl.id = p.credit_move_id
                                 JOIN account_move cm ON cm.id = cl.move_id
                                WHERE p.debit_move_id = aml.id
                                  AND p.max_date <= %(date_to)s
                                  AND cm.state = 'posted'
                                  AND cm.id NOT IN %(excluded)s
                                  AND cl.date <= %(date_to)s
                                  AND cl.account_id IN %(accounts)s), 0.0)
                   + COALESCE((SELECT SUM(p.amount)
                                 FROM account_partial_reconcile p
                                 JOIN account_move_line dl ON dl.id = p.debit_move_id
                                 JOIN account_move dm ON dm.id = dl.move_id
                                WHERE p.credit_move_id = aml.id
                                  AND p.max_date <= %(date_to)s
                                  AND dm.state = 'posted'
                                  AND dm.id NOT IN %(excluded)s
                                  AND dl.date <= %(date_to)s
                                  AND dl.account_id IN %(accounts)s), 0.0)
                   AS residual
              FROM account_move_line aml
              JOIN account_move am ON am.id = aml.move_id
             WHERE am.company_id = %(company)s
               AND am.state = 'posted'
               AND am.id NOT IN %(excluded)s
               AND aml.date <= %(date_to)s
               AND aml.account_id IN %(accounts)s
        """, {
            'date_to': self.date_end,
            'company': self.company_id.id,
            'accounts': tuple(accounts.ids),
            'excluded': self._get_excluded_move_ids(),
        })
        residual_by_line = {
            line_id: float(residual or 0.0)
            for line_id, residual in self.env.cr.fetchall()
            if abs(float(residual or 0.0)) >= 0.005
        }
        if not residual_by_line:
            return {'lines': [], 'total': 0.0}

        groups = {}
        move_lines = self.env['account.move.line'].browse(list(residual_by_line))
        for line in move_lines:
            partner = line.partner_id.commercial_partner_id
            move = line.move_id
            if partner:
                key = (partner.id, move.id)
            elif split_no_partner:
                key = (0, move.id)
            else:
                key = (0, 0)
            if date_source == 'invoice':
                doc_date = move.invoice_date or move.date
            else:
                doc_date = move.date

            group = groups.get(key)
            if group is None:
                group = groups[key] = {
                    'partner': partner,
                    'move': move,
                    'date': doc_date,
                    'amount': 0.0,
                }
            group['amount'] += residual_by_line[line.id]
            if doc_date and (not group['date'] or doc_date < group['date']):
                group['date'] = doc_date

        rows = []
        for key, group in groups.items():
            if abs(group['amount']) < 0.005:
                continue
            partner = group['partner']
            move = group['move']
            if partner:
                id_type = getattr(partner, 'l10n_latam_identification_type_id', False)
                rows.append({
                    'doc_type': (getattr(id_type, 'l10n_pe_vat_code', False) or '0')
                                if id_type else '0',
                    'doc_number': partner.vat or '-',
                    'name': partner.name or '',
                    'doc_ref': move.ref or move.name or '-',
                    'amount': group['amount'],
                    'date': group['date'],
                })
            else:
                split = key != (0, 0)
                rows.append({
                    'doc_type': '0',
                    'doc_number': '-',
                    'name': _('VARIOS (sin tercero asignado)'),
                    'doc_ref': (move.name or '-') if split else '-',
                    'amount': group['amount'],
                    'date': group['date'] if split else self.date_end,
                })

        rows.sort(key=lambda r: ((r['name'] or '').upper(), r['date'] or date.min))
        return {
            'lines': rows,
            'total': sum(r['amount'] for r in rows),
        }