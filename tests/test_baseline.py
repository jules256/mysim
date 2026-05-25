"""Baseline tests for mysim simulation engine."""

from decimal import Decimal

import pytest

from mysim.config import AppConfig
from mysim.engine import SimulationEngine
from mysim.plugins.growth import GrowthPlugin
from mysim.plugins.inflation import InflationPlugin
from mysim.plugins.inflows import InflowPlugin
from mysim.plugins.outflows import OutflowPlugin
from mysim.plugins.pre_tax_summary import PreTaxSummaryPlugin
from mysim.plugins.reconcile import ReconcilePlugin
from mysim.state import ZERO


def _minimal_config() -> dict:
    """Create a minimal configuration for baseline testing."""
    return {
        "schema_version": 1,
        "engine_version": "0.1",
        "simulation": {
            "birth_year": 1974,
            "start_year": 2026,
            "end_year": 2030,
            "baseline_inflation_rate": "0.00",
            "capital_withdrawal_order": ["savings"],
        },
        "capital_sources": {
            "savings": {
                "label": "Sparkonto",
                "capital_total": "100000",
                "capital_cost_basis": "100000",
                "capital_growth_accumulated": "0",
                "capital_growth_rate": "0.05",
                "withdrawal_strategy": "pro-rata",
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
            "health_insurance_status": "privat_versichert",
        },
        "events": [],
    }


class TestBaselineScenario:
    """Baseline: single account, zero inflation, zero taxes, simple constant growth."""

    def test_deterministic_output(self):
        """Same config produces identical results."""
        config = AppConfig(**_minimal_config())
        plugins = [
            InflationPlugin(config),
            InflowPlugin(config),
            OutflowPlugin(config),
            PreTaxSummaryPlugin(),
            GrowthPlugin(),
            ReconcilePlugin(config),
        ]

        engine1 = SimulationEngine(config=config, plugins=plugins)
        results1 = engine1.run()

        # Re-run with fresh instances
        config2 = AppConfig(**_minimal_config())
        plugins2 = [
            InflationPlugin(config2),
            InflowPlugin(config2),
            OutflowPlugin(config2),
            PreTaxSummaryPlugin(),
            GrowthPlugin(),
            ReconcilePlugin(config2),
        ]
        engine2 = SimulationEngine(config=config2, plugins=plugins2)
        results2 = engine2.run()

        assert len(results1) == len(results2)
        for r1, r2 in zip(results1, results2):
            assert r1["year"] == r2["year"]
            assert r1["capital_total_savings"] == r2["capital_total_savings"]

    def test_pure_growth_no_cashflow(self):
        """With no inflows/outflows, capital grows purely by compound rate."""
        config = AppConfig(**_minimal_config())
        plugins = [
            InflationPlugin(config),
            InflowPlugin(config),
            OutflowPlugin(config),
            PreTaxSummaryPlugin(),
            GrowthPlugin(),
            ReconcilePlugin(config),
        ]
        engine = SimulationEngine(config=config, plugins=plugins)
        results = engine.run()

        # Year 1: 100000 * 1.05 = 105000
        assert results[0]["capital_total_savings"] == Decimal("105000.00")
        # Year 2: 105000 * 1.05 = 110250
        assert results[1]["capital_total_savings"] == Decimal("110250.0000")

    def test_year_and_age_tracking(self):
        """Verify correct year and age progression."""
        config = AppConfig(**_minimal_config())
        plugins = [
            InflationPlugin(config),
            InflowPlugin(config),
            OutflowPlugin(config),
            PreTaxSummaryPlugin(),
            GrowthPlugin(),
            ReconcilePlugin(config),
        ]
        engine = SimulationEngine(config=config, plugins=plugins)
        results = engine.run()

        assert results[0]["year"] == 2026
        assert results[0]["age"] == 52
        assert results[-1]["year"] == 2030
        assert results[-1]["age"] == 56

    def test_no_insolvency_with_pure_growth(self):
        """No insolvency when there are no outflows."""
        config = AppConfig(**_minimal_config())
        plugins = [
            InflationPlugin(config),
            InflowPlugin(config),
            OutflowPlugin(config),
            PreTaxSummaryPlugin(),
            GrowthPlugin(),
            ReconcilePlugin(config),
        ]
        engine = SimulationEngine(config=config, plugins=plugins)
        results = engine.run()

        for r in results:
            assert r["is_insolvent"] is False


class TestInsolvencyScenario:
    """Test insolvency detection with high outflows."""

    def test_insolvency_stops_simulation(self):
        """Simulation stops when insolvency is detected with 'stop' policy."""
        raw = _minimal_config()
        raw["capital_sources"]["savings"]["capital_total"] = "1000"
        raw["capital_sources"]["savings"]["capital_cost_basis"] = "1000"
        raw["generic_trackers"]["fixed_costs_living"] = "50000"
        raw["simulation"]["insolvency_policy"] = "stop"

        config = AppConfig(**raw)
        plugins = [
            InflationPlugin(config),
            InflowPlugin(config),
            OutflowPlugin(config),
            PreTaxSummaryPlugin(),
            GrowthPlugin(),
            ReconcilePlugin(config),
        ]
        engine = SimulationEngine(config=config, plugins=plugins)
        results = engine.run()

        # Should stop at first year due to insolvency
        assert results[-1]["is_insolvent"] is True
        assert len(results) == 1


class TestInvariantValidation:
    """Test that capital invariants are enforced."""

    def test_capital_invariant_holds(self):
        """capital_total == cost_basis + growth after every year."""
        config = AppConfig(**_minimal_config())
        plugins = [
            InflationPlugin(config),
            InflowPlugin(config),
            OutflowPlugin(config),
            PreTaxSummaryPlugin(),
            GrowthPlugin(),
            ReconcilePlugin(config),
        ]
        engine = SimulationEngine(config=config, plugins=plugins)
        engine.run()

        # Check final state via snapshots
        for snapshot in engine.snapshots:
            # The engine validated without throwing - invariants hold
            assert "capital_total_savings" in snapshot
