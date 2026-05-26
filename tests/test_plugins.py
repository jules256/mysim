from decimal import Decimal

from mysim.config import AppConfig
from mysim.plugins.german_tax_insurance import GermanTaxInsurancePlugin
from mysim.plugins.growth import GrowthPlugin
from mysim.plugins.inflation import InflationPlugin
from mysim.plugins.inflows import InflowPlugin
from mysim.plugins.outflows import OutflowPlugin
from mysim.plugins.reconcile import ReconcilePlugin
from mysim.plugins.reconcile import ReconcilePlugin as Reconcile
from mysim.state import CapitalSource, LedgerEntry, SimulationState, ZERO


def _minimal_config_dict() -> dict:
    return {
        "schema_version": 1,
        "engine_version": "0.1",
        "simulation": {
            "birth_year": 1974,
            "start_year": 2026,
            "end_year": 2027,
            "baseline_inflation_rate": "0.02",
            "capital_withdrawal_order": ["savings"],
        },
        "capital_sources": {
            "savings": {
                "label": "Sparkonto",
                "capital_total": "100000",
                "capital_cost_basis": "100000",
                "capital_growth_accumulated": "0",
                "capital_growth_rate": "0.01",
                "withdrawal_strategy": "fifo",
            }
        },
        "generic_trackers": {
            "fixed_costs_living": "0",
            "pocket_money": "0",
            "pensions": [],
        },
        "german_plugin_config": {
            "income_tax_filing_status": "single",
            "confession_has_church_tax": False,
            "number_of_children": 0,
            "grundfreibetrag": "11604",
            "health_insurance_status": "freiwillig_versichert",
        },
        "events": [],
    }


def _make_state(config: AppConfig) -> SimulationState:
    source = CapitalSource(
        label="Sparkonto",
        capital_total=Decimal("100000"),
        capital_cost_basis=Decimal("100000"),
        capital_growth_accumulated=Decimal("0"),
        capital_growth_rate=Decimal("0.01"),
        withdrawal_strategy="fifo",
    )
    return SimulationState(
        year=2026,
        age=52,
        inflation_rate=config.simulation.baseline_inflation_rate,
        capital_sources={"savings": source},
        inflows={"salary": LedgerEntry(value=Decimal("50000"), label="Gehalt")},
        outflows={"costs": LedgerEntry(value=Decimal("25000"), label="Lebenshaltungskosten")},
        deductions={},
        capital_withdrawal_order=config.simulation.capital_withdrawal_order,
    )


def test_inflation_plugin_updates_baseline():
    raw = _minimal_config_dict()
    raw["events"] = [
        {
            "year": 2026,
            "label": "Anpassung Inflation",
            "plugin": "core_engine",
            "action": "update_baseline",
            "parameters": {"inflation_rate": "0.035"},
        }
    ]
    config = AppConfig(**raw)
    plugin = InflationPlugin(config)
    state = _make_state(config)
    state.year = 2026

    state = plugin.execute(state, None)

    assert state.inflation_rate == Decimal("0.035")


def test_inflow_plugin_handles_tax_free_event():
    raw = _minimal_config_dict()
    raw["events"] = [
        {
            "year": 2026,
            "label": "Erbschaft",
            "plugin": "inflow_tracker",
            "action": "one_time_inflow",
            "parameters": {"amount": "50000", "type": "tax_free"},
        }
    ]
    config = AppConfig(**raw)
    plugin = InflowPlugin(config)
    state = _make_state(config)
    state.year = 2026

    state = plugin.execute(state, None)

    assert "event_erbschaft" in state.inflows
    assert state.inflows["event_erbschaft"].is_tax_free is True
    assert state.inflows["event_erbschaft"].value == Decimal("50000")


def test_german_tax_insurance_plugin_adds_gkv_and_pv():
    raw = _minimal_config_dict()
    raw["german_plugin_config"]["health_insurance_status"] = "freiwillig_versichert"
    config = AppConfig(**raw)
    plugin = GermanTaxInsurancePlugin(config)
    state = _make_state(config)
    state.compute_summaries()

    state = plugin.execute(state, None)

    assert "gkv" in state.deductions
    assert state.deductions["gkv"].value > Decimal("0")
    assert "pv" in state.deductions
    assert state.deductions["pv"].value > Decimal("0")


def test_reconcile_with_allow_negative_capital_allows_debt():
    raw = _minimal_config_dict()
    raw["simulation"]["allow_negative_capital"] = True
    config = AppConfig(**raw)
    plugin = ReconcilePlugin(config)
    state = _make_state(config)
    state.capital_sources["savings"].capital_total = Decimal("1000")
    state.inflows = {"salary": LedgerEntry(value=Decimal("0"), label="Gehalt")}
    state.outflows = {"costs": LedgerEntry(value=Decimal("5000"), label="Kosten")}
    state.compute_summaries()
    state.allow_negative_capital = True

    state = plugin.execute(state, None)

    assert state.capital_sources["savings"].capital_total < Decimal("0")
    assert state.is_insolvent is False


def test_reconcile_withdraw_strategies():
    raw = _minimal_config_dict()
    config = AppConfig(**raw)
    plugin = ReconcilePlugin(config)

    fifo = CapitalSource(
        label="FIFO",
        capital_total=Decimal("1000"),
        capital_cost_basis=Decimal("800"),
        capital_growth_accumulated=Decimal("200"),
        capital_growth_rate=Decimal("0"),
        withdrawal_strategy="fifo",
    )
    state = _make_state(config)
    plugin._withdraw_from_source(state, "fifo", fifo, Decimal("300"))
    assert fifo.capital_cost_basis == Decimal("500")
    assert fifo.capital_growth_accumulated == Decimal("200")
    assert fifo.capital_total == Decimal("700")

    gain_first = CapitalSource(
        label="GrowthFirst",
        capital_total=Decimal("1000"),
        capital_cost_basis=Decimal("600"),
        capital_growth_accumulated=Decimal("400"),
        capital_growth_rate=Decimal("0"),
        withdrawal_strategy="gain-first",
    )
    plugin._withdraw_from_source(state, "gain_first", gain_first, Decimal("300"))
    assert gain_first.capital_growth_accumulated == Decimal("100")
    assert gain_first.capital_cost_basis == Decimal("600")
    assert gain_first.capital_total == Decimal("700")

    pro_rata = CapitalSource(
        label="ProRata",
        capital_total=Decimal("1000"),
        capital_cost_basis=Decimal("500"),
        capital_growth_accumulated=Decimal("500"),
        capital_growth_rate=Decimal("0"),
        withdrawal_strategy="pro-rata",
    )
    plugin._withdraw_from_source(state, "pro_rata", pro_rata, Decimal("200"))
    assert pro_rata.capital_cost_basis < Decimal("500")
    assert pro_rata.capital_growth_accumulated < Decimal("500")
    assert pro_rata.capital_total == Decimal("800")
