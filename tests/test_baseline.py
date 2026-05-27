"""Baseline tests for mysim simulation engine."""

from decimal import Decimal

import pytest

from mysim.config import AppConfig
from mysim.engine import SimulationEngine
from mysim.plugins.german_tax_insurance import GermanTaxInsurancePlugin
from mysim.plugins.growth import GrowthPlugin
from mysim.plugins.inflation import InflationPlugin
from mysim.plugins.inflows import InflowPlugin
from mysim.plugins.outflows import OutflowPlugin
from mysim.plugins.pre_tax_summary import PreTaxSummaryPlugin
from mysim.plugins.reconcile import ReconcilePlugin
from mysim.state import CapitalSource, ZERO


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

    def test_tax_free_inflow_is_excluded_from_taxable_income(self):
        """A tax-free one-time inflow should not increase income tax."""
        raw = _minimal_config()
        raw["events"] = [
            {
                "year": 2026,
                "label": "Erbschaft",
                "plugin": "inflow_tracker",
                "action": "one_time_inflow",
                "parameters": {"amount": "50000", "type": "tax_free"},
            }
        ]
        raw["german_plugin_config"]["health_insurance_status"] = "privat_versichert"
        raw["german_plugin_config"]["grundfreibetrag"] = "11604"

        config = AppConfig(**raw)
        plugins = [
            InflationPlugin(config),
            InflowPlugin(config),
            OutflowPlugin(config),
            PreTaxSummaryPlugin(),
            GermanTaxInsurancePlugin(config),
            GrowthPlugin(),
            ReconcilePlugin(config),
        ]
        engine = SimulationEngine(config=config, plugins=plugins)
        results = engine.run()

        assert results[0]["total_inflows"] == Decimal("50000")
        assert results[0]["total_deductions"] == Decimal("0")

    def test_pro_rata_withdrawal_avoids_fifo_gain_jump(self):
        """Pro-rata withdrawal smooths realized gain recognition compared to FIFO."""
        config = AppConfig(**_minimal_config())
        plugin = ReconcilePlugin(config)

        fifo_source = CapitalSource(
            label="Sparkonto",
            capital_total=Decimal("200000"),
            capital_cost_basis=Decimal("50000"),
            capital_growth_accumulated=Decimal("150000"),
            capital_growth_rate=Decimal("0.05"),
            withdrawal_strategy="fifo",
        )
        pro_rata_source = CapitalSource(
            label="Sparkonto",
            capital_total=Decimal("200000"),
            capital_cost_basis=Decimal("50000"),
            capital_growth_accumulated=Decimal("150000"),
            capital_growth_rate=Decimal("0.05"),
            withdrawal_strategy="pro-rata",
        )

        fifo_gains = [
            plugin._withdraw_from_source(fifo_source, Decimal("40000")),
            plugin._withdraw_from_source(fifo_source, Decimal("40000")),
        ]
        pro_rata_gains = [
            plugin._withdraw_from_source(pro_rata_source, Decimal("40000")),
            plugin._withdraw_from_source(pro_rata_source, Decimal("40000")),
        ]

        assert fifo_gains[0] == ZERO
        assert fifo_gains[1] > ZERO
        assert pro_rata_gains[0] > ZERO
        assert pro_rata_gains[1] > ZERO
        assert abs(pro_rata_gains[1] - pro_rata_gains[0]) < abs(
            fifo_gains[1] - fifo_gains[0]
        )

    def test_allow_negative_capital_continues_with_debt(self):
        """When negative capital is allowed, the simulation continues instead of stopping."""
        raw = _minimal_config()
        raw["capital_sources"]["savings"]["capital_total"] = "1000"
        raw["capital_sources"]["savings"]["capital_cost_basis"] = "1000"
        raw["generic_trackers"]["fixed_costs_living"] = "50000"
        raw["simulation"]["allow_negative_capital"] = True
        raw["simulation"]["insolvency_policy"] = "debt"
        raw["german_plugin_config"]["health_insurance_status"] = "privat_versichert"

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

        assert len(results) > 1
        assert results[0]["is_insolvent"] is False
        assert results[0]["capital_total_savings"] < Decimal("0")

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
