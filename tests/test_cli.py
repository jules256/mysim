import sys
from pathlib import Path

import pytest
import yaml

from mysim import cli as cli_module
from mysim.cli import load_config, build_plugins, setup_logging
from mysim.config import AppConfig


def _minimal_config_yaml() -> str:
    return yaml.safe_dump(
        {
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
                "health_insurance_status": "privat_versichert",
            },
            "events": [],
        }
    )


def test_load_config_and_build_plugins(tmp_path: Path):
    config_path = tmp_path / "scenario.yaml"
    config_path.write_text(_minimal_config_yaml(), encoding="utf-8")

    config = load_config(config_path)
    assert isinstance(config, AppConfig)
    assert config.simulation.start_year == 2026

    plugins = build_plugins(config)
    assert any(plugin.name() == "inflation" for plugin in plugins)
    assert any(plugin.name() == "german_tax_insurance" for plugin in plugins)


def test_cli_main_dry_run_exits_success(monkeypatch, tmp_path: Path):
    config_path = tmp_path / "scenario.yaml"
    config_path.write_text(_minimal_config_yaml(), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["mysim", "--dry-run", str(config_path)])

    with pytest.raises(SystemExit) as excinfo:
        cli_module.main()
    assert excinfo.value.code == 0


def test_setup_logging_sets_logger_with_handler():
    setup_logging(debug=True)
    import logging

    assert len(logging.getLogger().handlers) > 0
