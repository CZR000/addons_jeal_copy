import { AccountReport } from "@account_reports/components/account_report/account_report";
import { AccountReportFilters } from "@account_reports/components/account_report/filters/filters";

export class MulticurrencyRevaluationDualRateReportFilters extends AccountReportFilters {
    static template = "account_multicurrency_revaluation_dual_rate.MulticurrencyRevaluationDualRateReportFilters";

    //------------------------------------------------------------------------------------------------------------------
    // Custom filters
    //------------------------------------------------------------------------------------------------------------------
    async filterExchangeRate(ev, currencyId, rateType) {
        const validRateTypes = ['sale_rate', 'purchase_rate'];
        if (!validRateTypes.includes(rateType)) {
            console.error(`Invalid rateType: ${rateType}. Expected 'sale_rate' or 'purchase_rate'.`);
            return;
        }

        const rateKey = rateType === 'sale_rate' ? 'sale_rate' : 'purchase_rate';
        this.controller.options.currency_rates[currencyId][rateKey] = ev.currentTarget.value;
    }
}

AccountReport.registerCustomComponent(MulticurrencyRevaluationDualRateReportFilters);
