from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ApprovalRequest(models.Model):
    _inherit = 'approval.request'

    l10n_pe_advance_kind = fields.Selection(related='category_id.l10n_pe_advance_kind')
    l10n_pe_currency_id = fields.Many2one(
        comodel_name='res.currency',
        string='Moneda',
        default=lambda self: self.env.company.currency_id,
        help='Moneda del anticipo: el pago sale del diario de esa moneda.',
    )
    l10n_pe_employee_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Empleado',
        compute='_compute_l10n_pe_employee_id', store=True, readonly=False,
        check_company=True,
        help='Empleado que recibe el anticipo y luego lo rinde.',
    )
    l10n_pe_expense_sheet_id = fields.Many2one(
        comodel_name='hr.expense.sheet',
        string='Reposición del informe',
        readonly=True,
        copy=False,
        help='Informe de gastos del fondo de caja chica cuyo total repone esta solicitud.',
    )

    @api.depends('request_owner_id')
    def _compute_l10n_pe_employee_id(self):
        for request in self:
            request.l10n_pe_employee_id = request.request_owner_id.employee_id.filtered(
                lambda employee: employee.company_id == request.company_id
            ) or request.l10n_pe_employee_id

    # -------------------------------------------------------------------------
    # Pago del anticipo
    # -------------------------------------------------------------------------

    def _get_payment_employee(self):
        return self.l10n_pe_employee_id or super()._get_payment_employee()

    def _get_payment_journal(self):
        journal = super()._get_payment_journal()
        if not self.l10n_pe_advance_kind:
            return journal
        currency = self.l10n_pe_currency_id or self.company_id.currency_id
        journals = journal | self.category_id.l10n_pe_payment_journal_ids
        journal = journals.filtered(lambda j: (j.currency_id or j.company_id.currency_id) == currency)[:1]
        if not journal:
            raise UserError(_(
                'El tipo de aprobación "%(category)s" no tiene un diario de pago en %(currency)s. '
                'Agréguelo en "Diarios de pago por moneda".',
                category=self.category_id.name, currency=currency.name,
            ))
        return journal

    def _get_advance_account(self):
        self.ensure_one()
        company = self.company_id
        currency = self.l10n_pe_currency_id or company.currency_id
        if self.l10n_pe_advance_kind == 'petty_cash':
            account = company._get_hr_expense_petty_cash_account(currency)
        else:
            account = company._get_hr_expense_advance_account(currency)
        if not account:
            raise UserError(_(
                'Configure las "Cuentas de entregas a rendir" de la compañía %s '
                '(Gastos > Configuración > Ajustes).', company.name,
            ))
        return account

    def _create_and_open_payment(self):
        action = super()._create_and_open_payment()
        if self.l10n_pe_advance_kind:
            self.env['account.payment'].browse(action['res_id'])._l10n_pe_ensure_journal_entry()
        return action

    def _prepare_payment_vals(self):
        vals = super()._prepare_payment_vals()
        if self.l10n_pe_advance_kind:
            vals.update({
                'currency_id': (self.l10n_pe_currency_id or self.company_id.currency_id).id,
                'destination_account_id': self._get_advance_account().id,
            })
        return vals
