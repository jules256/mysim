from pathlib import Path
import sys

import yaml

from mysim.web import run as web_run
from mysim.web.app import create_app
from mysim.web.security import validate_scenario_name


def _example_scenario_data() -> dict:
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
            "health_insurance_status": "privat_versichert",
        },
        "events": [],
    }


def test_validate_scenario_name_rejects_invalid_characters():
    for name in ["../etc/passwd", "UPPERCASE", "contains space"]:
        try:
            validate_scenario_name(name)
            assert False, f"invalid scenario name {name} should not validate"
        except Exception:
            pass


def test_web_routes_workflow(tmp_path: Path):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    app = create_app(scenarios_dir=str(scenarios_dir))
    client = app.test_client()

    scenario_name = "baseline"
    scenario_file = scenarios_dir / f"{scenario_name}.yaml"
    scenario_file.write_text(yaml.safe_dump(_example_scenario_data()), encoding="utf-8")

    response = client.get("/")
    assert response.status_code == 200
    assert scenario_name in response.get_data(as_text=True)

    response = client.get(f"/scenario/{scenario_name}")
    assert response.status_code == 200
    assert "Simulationsparameter" in response.get_data(as_text=True)

    response = client.post(f"/scenario/{scenario_name}/run", data={})
    assert response.status_code == 302
    result_location = response.headers["Location"]
    assert f"/scenario/{scenario_name}/results" in result_location
    assert "cfg=" in result_location

    response = client.get(result_location)
    assert response.status_code == 200
    assert "Ergebnisse" in response.get_data(as_text=True)

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(result_location)
    cfg_param = parse_qs(parsed.query)["cfg"][0]

    response = client.get(f"/scenario/{scenario_name}/export/csv?cfg={cfg_param}")
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith("text/csv")
    assert "year" in response.get_data(as_text=True)


def test_web_export_xlsx_and_trace(tmp_path: Path):
    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    app = create_app(scenarios_dir=str(scenarios_dir))
    client = app.test_client()

    scenario_name = "baseline"
    scenario_file = scenarios_dir / f"{scenario_name}.yaml"
    scenario_file.write_text(yaml.safe_dump(_example_scenario_data()), encoding="utf-8")

    response = client.post(f"/scenario/{scenario_name}/run", data={})
    assert response.status_code == 302
    result_location = response.headers["Location"]

    from urllib.parse import urlparse, parse_qs
    parsed = urlparse(result_location)
    cfg_param = parse_qs(parsed.query)["cfg"][0]

    response = client.get(f"/scenario/{scenario_name}/export/xlsx?cfg={cfg_param}")
    assert response.status_code == 200
    assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in response.headers["Content-Type"]

    response = client.get(f"/scenario/{scenario_name}/trace/2026?cfg={cfg_param}")
    assert response.status_code == 200
    assert "Ergebnis" in response.get_data(as_text=True)


def test_web_run_main_invokes_flask_run(monkeypatch, tmp_path: Path):
    called = {}

    class FakeApp:
        def run(self, host, port, debug):
            called["host"] = host
            called["port"] = port
            called["debug"] = debug

    def fake_create_app(scenarios_dir: str):
        assert scenarios_dir == str(tmp_path)
        return FakeApp()

    monkeypatch.setattr(web_run, "create_app", fake_create_app)
    monkeypatch.setattr(sys, "argv", [
        "mysim-web",
        "--host",
        "127.0.0.1",
        "--port",
        "5050",
        "--scenarios",
        str(tmp_path),
        "--debug",
    ])

    web_run.main()

    assert called["host"] == "127.0.0.1"
    assert called["port"] == 5050
    assert called["debug"] is True
