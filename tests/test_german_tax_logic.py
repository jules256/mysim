from decimal import Decimal
from mysim.config import AppConfig, GermanPluginConfig
from mysim.plugins.german_tax_insurance import GermanTaxInsurancePlugin
from mysim.state import SimulationState, CapitalSource, LedgerEntry, ZERO

def test_progressive_tax_splitting_married():
    # Tax on 100k married should be 2 * tax(50k)
    # Single tax on 50k - 11604 = 38396
    # 38396 is in Zone 2: 17005 * 0.19 + (38396 - 17005) * 0.33 = 3230.95 + 7059.03 = 10289.98
    # Total married tax = 2 * 10289.98 = 20579.96

    cfg_dict = {
        "schema_version": 1,
        "engine_version": "0.1",
        "simulation": {"birth_year": 1974},
        "german_plugin_config": {
            "income_tax_filing_status": "married",
            "grundfreibetrag": "11604",
        }
    }
    config = AppConfig(**cfg_dict)
    plugin = GermanTaxInsurancePlugin(config)

    state = SimulationState(
        year=2026, age=52, inflation_rate=ZERO,
        inflows={"salary": LedgerEntry(value=Decimal("100000"), label="Gehalt")}
    )
    state.compute_summaries()

    state = plugin.execute(state, None)

    # We expect roughly 20k-21k based on simplified formula
    assert Decimal("20000") < state.deductions["income_tax"].value < Decimal("22000")

def test_capital_gains_tax_with_pauschbetrag_and_teilfreistellung():
    # 10k equity gain, 5k other gain. Married (2000 Pauschbetrag).
    # 1. Pauschbetrag 2000 applied to 5k other -> 3k remaining other.
    # 2. Teilfreistellung 30% on 10k equity -> 7k taxable equity.
    # Total taxable = 3k + 7k = 10k.
    # Tax = 10k * 0.25 = 2.5k.
    # Soli = 2.5k * 0.055 = 137.5.
    # Total = 2637.5.

    cfg_dict = {
        "schema_version": 1,
        "engine_version": "0.1",
        "simulation": {"birth_year": 1974},
        "german_plugin_config": {
            "income_tax_filing_status": "married",
            "sparer_pauschbetrag": "1000", # Married -> 2000
            "stock_fund_tax_exempt_rate": "0.30",
            "fixed_capital_gains_tax_rate": "0.25",
        }
    }
    config = AppConfig(**cfg_dict)
    plugin = GermanTaxInsurancePlugin(config)

    state = SimulationState(
        year=2026, age=52, inflation_rate=ZERO,
        capital_sources={
            "equity": CapitalSource(label="Equity", capital_total=ZERO, capital_cost_basis=ZERO, capital_growth_accumulated=ZERO, capital_growth_rate=ZERO, withdrawal_strategy="fifo", is_equity_fund=True),
            "other": CapitalSource(label="Other", capital_total=ZERO, capital_cost_basis=ZERO, capital_growth_accumulated=ZERO, capital_growth_rate=ZERO, withdrawal_strategy="fifo", is_equity_fund=False)
        },
        inflows={
            "realized_gain_equity": LedgerEntry(value=Decimal("10000"), label="Gain Equity"),
            "realized_gain_other": LedgerEntry(value=Decimal("5000"), label="Gain Other")
        }
    )
    state.compute_summaries()

    state = plugin.execute(state, None)

    assert state.deductions["capital_gains_tax"].value == Decimal("2637.50")
