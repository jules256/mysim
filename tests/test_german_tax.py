"""Tests for German tax and insurance logic."""

from decimal import Decimal
import pytest
from mysim.config import AppConfig
from mysim.engine import SimulationEngine
from mysim.plugins.german_tax_insurance import GermanTaxInsurancePlugin
from mysim.plugins.pre_tax_summary import PreTaxSummaryPlugin
from mysim.plugins.inflows import InflowPlugin
from mysim.state import ZERO, LedgerEntry
from mysim.plugin import Plugin

def _base_tax_config() -> dict:
    return {
        "schema_version": 1,
        "engine_version": "0.1",
        "simulation": {
            "birth_year": 1980,
            "start_year": 2024,
            "end_year": 2025,
            "baseline_inflation_rate": "0.00",
        },
        "capital_sources": {},
        "generic_trackers": {
            "fixed_costs_living": "0",
            "pocket_money": "0",
            "pensions": [],
        },
        "german_plugin_config": {
            "income_tax_filing_status": "single",
            "grundfreibetrag": "11604", # 2024
            "health_insurance_status": "privat_versichert",
        },
        "events": [],
    }

class TestGermanTax:
    def test_progressive_tax_single_below_threshold(self):
        raw = _base_tax_config()
        # Pension below Grundfreibetrag
        raw["generic_trackers"]["pensions"] = [
            {"name": "p1", "label": "P", "amount": "10000", "start_year": 2024}
        ]
        config = AppConfig(**raw)
        engine = SimulationEngine(config=config, plugins=[
            InflowPlugin(config),
            PreTaxSummaryPlugin(),
            GermanTaxInsurancePlugin(config)
        ])
        results = engine.run()
        assert results[0].get("deductions_income_tax", ZERO) == ZERO

    def test_progressive_tax_single_above_threshold(self):
        raw = _base_tax_config()
        # 50000 income. Grundfreibetrag 11604. Taxable 38396.
        # Bracket 1: 17005 * 0.19 = 3230.95
        # Bracket 2: (38396 - 17005) * 0.33 = 21391 * 0.33 = 7059.03
        # Total approx: 10289.98
        raw["generic_trackers"]["pensions"] = [
            {"name": "p1", "label": "P", "amount": "50000", "start_year": 2024}
        ]
        config = AppConfig(**raw)
        engine = SimulationEngine(config=config, plugins=[
            InflowPlugin(config),
            PreTaxSummaryPlugin(),
            GermanTaxInsurancePlugin(config)
        ])
        results = engine.run()
        tax = results[0].get("deductions_income_tax")
        assert tax > Decimal("10000")
        assert tax < Decimal("11000")

    def test_progressive_tax_married_splitting(self):
        raw = _base_tax_config()
        raw["german_plugin_config"]["income_tax_filing_status"] = "married"
        # 100000 total income. Splitting income 50000.
        # Single tax on (50000 - 11604) = 38396 should be same as above approx 10289.98.
        # Total married tax approx 20579.96
        raw["generic_trackers"]["pensions"] = [
            {"name": "p1", "label": "P", "amount": "100000", "start_year": 2024}
        ]
        config = AppConfig(**raw)
        engine = SimulationEngine(config=config, plugins=[
            InflowPlugin(config),
            PreTaxSummaryPlugin(),
            GermanTaxInsurancePlugin(config)
        ])
        results = engine.run()
        tax = results[0].get("deductions_income_tax")
        assert tax > Decimal("20000")
        assert tax < Decimal("22000")

    def test_capital_gains_tax_with_pauschbetrag(self):
        raw = _base_tax_config()
        raw["german_plugin_config"]["sparer_pauschbetrag"] = "1000"
        config = AppConfig(**raw)

        class MockGainPlugin(Plugin):
            def name(self): return "mock_gain"
            def priority(self): return -1
            def hooks(self): return [PreTaxSummaryPlugin().hooks()[0]]
            def execute(self, state, hook):
                state.inflows["realized_gain_test"] = LedgerEntry(
                    value=Decimal("3000"), label="Gain", is_cash_flow=False
                )
                return state

        engine = SimulationEngine(config=config, plugins=[
            MockGainPlugin(),
            PreTaxSummaryPlugin(),
            GermanTaxInsurancePlugin(config)
        ])
        results = engine.run()
        # (3000 - 1000) * 0.25 = 500
        assert results[0].get("deductions_capital_gains_tax") == Decimal("500.00")

    def test_capital_gains_tax_with_teilfreistellung(self):
        raw = _base_tax_config()
        raw["german_plugin_config"]["sparer_pauschbetrag"] = "0"
        raw["capital_sources"] = {
            "fund": {
                "label": "Equity Fund",
                "capital_total": "1000",
                "capital_cost_basis": "1000",
                "capital_growth_accumulated": "0",
                "capital_growth_rate": "0",
                "is_equity_fund": True
            }
        }
        config = AppConfig(**raw)

        class MockGainPlugin(Plugin):
            def name(self): return "mock_gain"
            def priority(self): return -1
            def hooks(self): return [PreTaxSummaryPlugin().hooks()[0]]
            def execute(self, state, hook):
                # Ensure the key is realized_gain_{account_key}
                state.inflows["realized_gain_fund"] = LedgerEntry(
                    value=Decimal("1000"), label="Gain", is_cash_flow=False
                )
                return state

        engine = SimulationEngine(config=config, plugins=[
            MockGainPlugin(),
            PreTaxSummaryPlugin(),
            GermanTaxInsurancePlugin(config)
        ])
        results = engine.run()
        # 1000 gain. Teilfreistellung 30% -> 700 taxable.
        # 700 * 0.25 = 175
        assert results[0].get("deductions_capital_gains_tax") == Decimal("175.00")

    def test_capital_gains_tax_key_lookup_regression(self):
        """Verify that the tax plugin correctly finds equity status via account key."""
        raw = _base_tax_config()
        raw["german_plugin_config"]["sparer_pauschbetrag"] = "0"
        raw["capital_sources"] = {
            "my_equity_fund": {
                "label": "Some Long Label With Spaces",
                "capital_total": "1000",
                "capital_cost_basis": "1000",
                "capital_growth_accumulated": "0",
                "capital_growth_rate": "0",
                "is_equity_fund": True
            }
        }
        config = AppConfig(**raw)

        class MockGainPlugin(Plugin):
            def name(self): return "mock_gain"
            def priority(self): return -1
            def hooks(self): return [PreTaxSummaryPlugin().hooks()[0]]
            def execute(self, state, hook):
                # The key should match the config key: realized_gain_my_equity_fund
                state.inflows["realized_gain_my_equity_fund"] = LedgerEntry(
                    value=Decimal("1000"), label="Realized Gain (Some Long Label With Spaces)", is_cash_flow=False
                )
                return state

        engine = SimulationEngine(config=config, plugins=[
            MockGainPlugin(),
            PreTaxSummaryPlugin(),
            GermanTaxInsurancePlugin(config)
        ])
        results = engine.run()
        # If lookup works, Teilfreistellung is applied: 1000 * 0.7 * 0.25 = 175.
        # If lookup fails, it's 1000 * 0.25 = 250.
        assert results[0].get("deductions_capital_gains_tax") == Decimal("175.00")
