"""Flask routes for the mysim web UI."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml
from flask import (
    Blueprint,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from mysim.config import AppConfig
from mysim.engine import SimulationEngine
from mysim.plugins.german_tax_insurance import GermanTaxInsurancePlugin
from mysim.plugins.growth import GrowthPlugin
from mysim.plugins.inflation import InflationPlugin
from mysim.plugins.inflows import InflowPlugin
from mysim.plugins.outflows import OutflowPlugin
from mysim.plugins.pre_tax_summary import PreTaxSummaryPlugin
from mysim.plugins.reconcile import ReconcilePlugin
from mysim.web.exports import cleanup_old_exports, generate_csv, generate_xlsx
from mysim.web.security import rate_limited, validate_scenario_name

logger = logging.getLogger(__name__)

bp = Blueprint("main", __name__)


# --- Helper functions ---


def _get_scenarios_dir() -> Path:
    return current_app.config["SCENARIOS_DIR"]


def _list_scenarios() -> list[str]:
    """List all valid scenario files in the scenarios directory."""
    scenarios_dir = _get_scenarios_dir()
    if not scenarios_dir.exists():
        return []
    scenarios = []
    for f in sorted(scenarios_dir.iterdir()):
        if f.suffix == ".yaml" and f.stat().st_size <= current_app.config["MAX_YAML_SIZE"]:
            name = f.stem
            # Validate name format
            from mysim.web.security import SCENARIO_NAME_PATTERN
            if SCENARIO_NAME_PATTERN.match(name) and len(name) <= 64:
                scenarios.append(name)
    return scenarios


def _load_scenario_yaml(name: str) -> dict:
    """Load raw YAML data for a scenario."""
    scenarios_dir = _get_scenarios_dir()
    filepath = scenarios_dir / f"{name}.yaml"
    if not filepath.exists():
        abort(404, description=f"Scenario '{name}' does not exist.")
    if filepath.stat().st_size > current_app.config["MAX_YAML_SIZE"]:
        abort(400, description="Configuration file exceeds maximum size limit.")
    with open(filepath, "r") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        abort(400, description="Invalid YAML: root must be a mapping.")
    return data


def _extract_simple_params(data: dict) -> dict[str, Any]:
    """Extract simple scalar parameters for form inputs."""
    simple = {}
    sim = data.get("simulation", {})
    for key in ("birth_year", "start_year", "end_year", "baseline_inflation_rate",
                "insolvency_policy"):
        if key in sim:
            simple[f"simulation.{key}"] = sim[key]

    german = data.get("german_plugin_config", {})
    for key in ("income_tax_filing_status", "confession_has_church_tax",
                "number_of_children", "grundfreibetrag", "sparer_pauschbetrag",
                "health_insurance_status", "gkv_contribution_rate",
                "gkv_additional_contribution", "gkv_beitragsbemessungsgrenze_annual"):
        if key in german:
            simple[f"german_plugin_config.{key}"] = german[key]

    trackers = data.get("generic_trackers", {})
    for key in ("fixed_costs_living", "pocket_money"):
        if key in trackers:
            simple[f"generic_trackers.{key}"] = trackers[key]

    return simple


def _extract_complex_params(data: dict) -> dict[str, str]:
    """Extract complex structured parameters as YAML text blocks."""
    complex_params = {}

    if "capital_sources" in data:
        complex_params["capital_sources"] = yaml.dump(
            data["capital_sources"], default_flow_style=False, allow_unicode=True
        )

    if "events" in data:
        complex_params["events"] = yaml.dump(
            data["events"], default_flow_style=False, allow_unicode=True
        )

    withdrawal_order = data.get("simulation", {}).get("capital_withdrawal_order")
    if withdrawal_order:
        complex_params["capital_withdrawal_order"] = yaml.dump(
            withdrawal_order, default_flow_style=False, allow_unicode=True
        )

    pensions = data.get("generic_trackers", {}).get("pensions")
    if pensions:
        complex_params["pensions"] = yaml.dump(
            pensions, default_flow_style=False, allow_unicode=True
        )

    return complex_params


def _apply_form_mutations(data: dict, form: dict) -> dict:
    """Apply form field mutations to the raw YAML data."""
    import copy
    data = copy.deepcopy(data)

    # Apply simple scalar overrides
    for key, value in form.items():
        if key.startswith("simple."):
            path = key[7:]  # strip "simple."
            parts = path.split(".")
            if len(parts) == 2:
                section, field = parts
                if section not in data:
                    data[section] = {}
                data[section][field] = _coerce_value(value)

    # Apply complex YAML block overrides
    for key in ("capital_sources", "events", "capital_withdrawal_order", "pensions"):
        form_key = f"complex.{key}"
        if form_key in form and form[form_key].strip():
            try:
                parsed = yaml.safe_load(form[form_key])
                if key == "capital_sources":
                    data["capital_sources"] = parsed
                elif key == "events":
                    data["events"] = parsed
                elif key == "capital_withdrawal_order":
                    if "simulation" not in data:
                        data["simulation"] = {}
                    data["simulation"]["capital_withdrawal_order"] = parsed
                elif key == "pensions":
                    if "generic_trackers" not in data:
                        data["generic_trackers"] = {}
                    data["generic_trackers"]["pensions"] = parsed
            except yaml.YAMLError as e:
                abort(400, description=f"YAML syntax error in '{key}': {e}")

    return data


def _coerce_value(value: str) -> Any:
    """Coerce a form string value to the appropriate Python type."""
    if value.lower() in ("true", "yes"):
        return True
    if value.lower() in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        # Keep as string for Decimal handling by Pydantic
        Decimal(value)
        return float(value)
    except (InvalidOperation, ValueError):
        pass
    return value


def _run_simulation(config: AppConfig) -> list[dict[str, Any]]:
    """Execute the simulation with all plugins."""
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
    return engine.run()


def _get_all_columns(results: list[dict[str, Any]]) -> list[str]:
    """Get all available column keys from results."""
    if not results:
        return []
    return [k for k in results[0].keys() if k != "traces"]


def _filter_columns(results: list[dict[str, Any]], cols: list[str]) -> list[str]:
    """Filter and validate requested columns against available ones."""
    available = _get_all_columns(results)
    if not cols:
        return available
    return [c for c in cols if c in available]


# --- Routes ---


@bp.route("/")
def index():
    """Scenario browser - lists available scenarios."""
    scenarios = _list_scenarios()
    return render_template("index.html", scenarios=scenarios)


@bp.route("/scenario/<name>")
def configure(name: str):
    """Configuration view - editable form for scenario parameters."""
    name = validate_scenario_name(name)
    data = _load_scenario_yaml(name)

    simple_params = _extract_simple_params(data)
    complex_params = _extract_complex_params(data)

    return render_template(
        "configure.html",
        scenario_name=name,
        simple_params=simple_params,
        complex_params=complex_params,
    )


@bp.route("/scenario/<name>/run", methods=["POST"])
@rate_limited
def run_simulation(name: str):
    """Execute simulation with form mutations (PRG: POST step)."""
    name = validate_scenario_name(name)
    data = _load_scenario_yaml(name)

    # Apply form mutations
    data = _apply_form_mutations(data, request.form)

    # Validate configuration
    try:
        config = AppConfig(**data)
    except Exception as e:
        logger.error("Configuration error for scenario '%s': %s", name, e)
        return render_template(
            "error.html",
            error_title="Konfigurationsfehler",
            error_message=str(e),
            scenario_name=name,
        ), 400

    # Enable debug for traces
    config.simulation.debug = True

    # Run simulation
    try:
        results = _run_simulation(config)
    except Exception as e:
        logger.error("Simulation failed for scenario '%s': %s", name, e)
        return render_template(
            "error.html",
            error_title="Simulationsfehler",
            error_message=str(e),
            scenario_name=name,
        ), 500

    # Store results transiently via URL params (redirect to GET view)
    # For simplicity, store in app-level cache keyed by scenario name
    # (single-user assumption per spec)
    current_app.config.setdefault("_results_cache", {})
    current_app.config["_results_cache"][name] = results

    # Get column selection from form
    cols = request.form.get("cols", "")
    return redirect(url_for("main.results", name=name, cols=cols))


@bp.route("/scenario/<name>/results")
def results(name: str):
    """Results view - displays simulation output table (PRG: GET step)."""
    name = validate_scenario_name(name)

    cache = current_app.config.get("_results_cache", {})
    sim_results = cache.get(name)

    if sim_results is None:
        return redirect(url_for("main.configure", name=name))

    # Column selection from URL params
    cols_param = request.args.get("cols", "")
    requested_cols = [c.strip() for c in cols_param.split(",") if c.strip()] if cols_param else []

    all_columns = _get_all_columns(sim_results)
    active_columns = _filter_columns(sim_results, requested_cols) if requested_cols else all_columns

    return render_template(
        "results.html",
        scenario_name=name,
        results=sim_results,
        all_columns=all_columns,
        active_columns=active_columns,
        cols_param=cols_param,
    )


@bp.route("/scenario/<name>/trace/<int:year>")
def get_trace(name: str, year: int):
    """AJAX endpoint for lazy-loading derivation traces."""
    name = validate_scenario_name(name)

    cache = current_app.config.get("_results_cache", {})
    sim_results = cache.get(name)

    if sim_results is None:
        abort(404, description="No simulation results available.")

    # Find the trace for the requested year
    for row in sim_results:
        if row.get("year") == year:
            traces = row.get("traces", [])
            # Depth limit: max 20 steps per trace
            limited_traces = []
            for trace in traces[:20]:
                if "steps" in trace:
                    trace = {**trace, "steps": trace["steps"][:20]}
                limited_traces.append(trace)
            return render_template("trace_fragment.html", traces=limited_traces, year=year)

    abort(404, description=f"No trace found for year {year}.")


@bp.route("/scenario/<name>/export/csv")
def export_csv(name: str):
    """Export simulation results as CSV."""
    name = validate_scenario_name(name)

    cache = current_app.config.get("_results_cache", {})
    sim_results = cache.get(name)

    if sim_results is None:
        abort(404, description="No simulation results available. Run the simulation first.")

    filename, content = generate_csv(sim_results, name)

    # Clean up old exports
    cleanup_old_exports(current_app.config["EXPORT_DIR"])

    # Save and serve
    export_path = current_app.config["EXPORT_DIR"] / filename
    export_path.write_text(content, encoding="utf-8-sig")

    return send_file(
        export_path,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename,
    )


@bp.route("/scenario/<name>/export/xlsx")
def export_xlsx(name: str):
    """Export simulation results as XLSX."""
    name = validate_scenario_name(name)

    cache = current_app.config.get("_results_cache", {})
    sim_results = cache.get(name)

    if sim_results is None:
        abort(404, description="No simulation results available. Run the simulation first.")

    include_traces = request.args.get("traces", "0") == "1"
    filename, xlsx_bytes = generate_xlsx(sim_results, name, include_traces=include_traces)

    # Clean up old exports
    cleanup_old_exports(current_app.config["EXPORT_DIR"])

    # Save and serve
    export_path = current_app.config["EXPORT_DIR"] / filename
    export_path.write_bytes(xlsx_bytes)

    return send_file(
        export_path,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )


# --- Error handlers ---


@bp.app_errorhandler(404)
def not_found(e):
    return render_template(
        "error.html",
        error_title="Nicht gefunden",
        error_message=str(e.description) if hasattr(e, "description") else "Seite nicht gefunden.",
        scenario_name=None,
    ), 404


@bp.app_errorhandler(400)
def bad_request(e):
    return render_template(
        "error.html",
        error_title="Fehlerhafte Anfrage",
        error_message=str(e.description) if hasattr(e, "description") else "Ungültige Eingabe.",
        scenario_name=None,
    ), 400


@bp.app_errorhandler(429)
def rate_limit_exceeded(e):
    return render_template(
        "error.html",
        error_title="Zu viele Anfragen",
        error_message=str(e.description) if hasattr(e, "description") else "Bitte warten Sie einen Moment.",
        scenario_name=None,
    ), 429


@bp.app_errorhandler(500)
def internal_error(e):
    return render_template(
        "error.html",
        error_title="Serverfehler",
        error_message="Ein interner Fehler ist aufgetreten.",
        scenario_name=None,
    ), 500
