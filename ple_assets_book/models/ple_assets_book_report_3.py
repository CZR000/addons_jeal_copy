from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AccountAsset(models.Model):
    _inherit = 'account.asset'

    contract_number = fields.Char(string="Nro. del contrato de arrendamiento Financiero")


class PleAssetsBook(models.Model):
    _inherit = 'ple.report.assets.book'

    def get_data_report_03(self):
        accounts_with_groups = self.env['account.account'].search([])
        account_group_map = {acc.id: (acc.group_id.id, acc.group_id.code_prefix_start) for acc in accounts_with_groups if acc.group_id}
        
        query_data_1 = """
            CREATE OR REPLACE FUNCTION get_balance(am_id INT, OUT amount_pe FLOAT) AS $$
            BEGIN
                SELECT aml.balance  INTO amount_pe
                FROM account_move am
                LEFT JOIN account_move_line aml ON aml.move_id = am.id
                LEFT JOIN account_account   acc ON acc.id=aml.account_id             
                WHERE 
                am.id = am_id  
                and acc.ple_selection in ('assets_book_acquisition_asset','assets_book_improvements_asset',
                'assets_book_other_asset','assets_book_voluntary_revaluation_asset',
                'assets_book_revaluation_reorganization_asset','assets_book_revaluation_other_asset',
                'assets_book_inflation_asset');
            END;
            $$ 
            LANGUAGE plpgsql;

            SELECT 
                validate_string(translate(COALESCE(am.name, aa.name), ' ', ''), 40) as cuo,
                COALESCE(aml.ple_correlative, 'M000000001') as ple_correlative,
                aa.asset_catalog_code as asset_catalog_code,
                validate_string(COALESCE(aa.contract_number, ''), 20) as contract_number,
                TO_CHAR(aa.acquisition_date,'DD/MM/YYYY') as acquisition_date,
                COALESCE(aa.asset_code,'SC01') as asset_code,
                TO_CHAR(COALESCE(aa.first_depreciation_date_import, COALESCE(aa.prorata_date, aa.acquisition_date)), 'DD/MM/YYYY') as asset_date_init,
                aa.method_number as method_number,
                aa.original_value as original_value,
                aa.id as id,
                am.exchange_rate as exchange_rate,
                get_balance(am.id) as value_acquisition_local,
                aa.account_asset_id as account_id
            FROM account_asset aa
                JOIN asset_move_line_rel amlr  ON  amlr.asset_id=aa.id
                LEFT JOIN account_move_line aml     ON  amlr.line_id=aml.id
                LEFT JOIN account_move am           ON  aml.move_id=am.id
                LEFT JOIN account_account  acc      ON  acc.id=aa.account_asset_id
            WHERE
                aa.acquisition_date <= '{date_end}' AND
                aa.company_id='{company_id}'  AND
                contract_number IS NOT NULL AND
                aa.state not in ('draft', 'cancelled')
                AND am.id = (
                    SELECT MIN(am.id) 
                    FROM account_move am
                    LEFT JOIN account_move_line aml ON aml.move_id = am.id
                    WHERE am.asset_id = aa.id
                )
        """.format(
            start_date=self.date_start,
            date_end=self.date_end,
            company_id=self.company_id.id,
        )

        query_data_2 = """
            CREATE OR REPLACE FUNCTION get_original_local(date_start TIMESTAMP, 
                                                    date_end TIMESTAMP , 
                                                    asset_id INTEGER,
                                                    OUT amount_pe FLOAT) AS $$
        BEGIN
            SELECT 
            aa.original_value INTO amount_pe
            FROM account_asset aa
            LEFT JOIN account_account  acc ON  acc.id=aa.account_asset_id
            WHERE aa.id=asset_id;
        END;
        $$ 
        LANGUAGE plpgsql;

            SELECT
                validate_string(translate(COALESCE(aa.name), ' ', ''), 40) as cuo,
                COALESCE('M000000001') as ple_correlative,
                aa.asset_catalog_code as asset_catalog_code,
                validate_string(COALESCE(aa.contract_number, ''), 20) as contract_number,
                TO_CHAR(aa.acquisition_date,'DD/MM/YYYY') as acquisition_date,
                COALESCE(aa.asset_code,'SC01') as asset_code,
                TO_CHAR(COALESCE(aa.first_depreciation_date_import, COALESCE(aa.prorata_date, aa.acquisition_date)), 'DD/MM/YYYY') as asset_date_init,
                aa.method_number as method_number,
                aa.original_value as original_value,
                aa.id as id,
                am.exchange_rate as exchange_rate,
                get_original_local('{start_date}','{date_end}',aa.id) as value_acquisition_local,
                aa.account_asset_id as account_id
            FROM account_asset aa
                LEFT JOIN asset_move_line_rel amlr  ON  amlr.asset_id=aa.id
                LEFT JOIN account_move_line aml     ON  amlr.line_id=aml.id
                LEFT JOIN account_move am           ON  aml.move_id=am.id   
                LEFT JOIN account_account  acc      ON  acc.id=aa.account_asset_id
            WHERE
                aa.acquisition_date <= '{date_end}' AND
                aa.company_id='{company_id}'  AND
                contract_number IS NOT NULL AND
                aa.state not in ('draft', 'cancelled')
        """.format(
            start_date=self.date_start,
            date_end=self.date_end,
            company_id=self.company_id.id,
        )

        try:
            data_1 , data_2 = [],[]
            self.env.cr.execute(query_data_1)
            data_1 = self.env.cr.dictfetchall()

            for row in data_1:
                account_id = row.get('account_id')
                if account_id in account_group_map:
                    group_id, code_prefix_start = account_group_map[account_id]
                    row['code_prefix_start'] = code_prefix_start

            self.env.cr.execute(query_data_2)
            data_2 = self.env.cr.dictfetchall()

            for row in data_2:
                account_id = row.get('account_id')
                if account_id in account_group_map:
                    group_id, code_prefix_start = account_group_map[account_id]
                    row['code_prefix_start'] = code_prefix_start
            
            data_2 = [row for row in data_2 if row.get('code_prefix_start') == '33']

            filtro = lambda elem: elem['id'] not in [e['id'] for e in data_1]
            data_filter = list(filter(filtro, data_2))

            data = data_1 + data_filter

        except Exception as error:
            raise ValidationError(f'Error al ejecutar la queries, comunicar al administrador: \n {error}')

        return data
