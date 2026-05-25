"""CLI entry point for mysim."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from mysim.config import AppConfig
from mysim.engine import SimulationEngine
from mysim.output import results_to_json, results_to_table
from mysim.plugins.german_tax_insurance import GermanTaxInsurancePlugin
from mysim.plugins.growth import GrowthPlugin
from mysim.plugins.inflation import InflationPlugin
from mysim.plugins.inflows import InflowPlugin
from mysim.plugins.outflows import OutflowPlugin
from mysim.plugins.pre_tax_summary import PreTaxSummaryPlugin
from mysim.plugins.reconcile import ReconcilePlugin


def setup_logging(debug: bool = False) -> None:
    """Configure structured logging."""
    level = logging.DEBUG if debug else logging.INFO
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            json.dumps(
                {
                    "time": "%(asctime)s",
                    "level": "%(levelname)s",
                    "module": "%(name)s",
                    "message": "%(message)s",
                }
            )
        )
    )
    logging.basicConfig(level=level, handlers=[handler])


def load_config(config_path: Path) -> AppConfig:
    """Load and validate configuration from a YAML file."""
    with open(config_path, "r") as f:
        raw = yaml.safe_load(f)
    return AppConfig(**raw)


def build_plugins(config: AppConfig) -> list:
    """Instantiate all default plugins."""
    return [
        InflationPlugin(config),
        InflowPlugin(config),
        OutflowPlugin(config),
        PreTaxSummaryPlugin(),
        GermanTaxInsurancePlugin(config),
        GrowthPlugin(),
        ReconcilePlugin(config),
    ]


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="mysim - Financial Simulation Engine"
    )
    parser.add_argument(
        "config", type=Path, help="Path to the YAML configuration file"
    )
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable debug mode with traces"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration without running simulation",
    )
    parser.add_argument(
        "--output", "-o", type=Path, help="Output file path (default: stdout)"
    )

    args = parser.parse_args()

    setup_logging(debug=args.debug)

    # Load and validate config
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(1)

    if args.debug:
        config.simulation.debug = True

    # Dry run mode: validate only
    if args.dry_run:
        print("Configuration valid.", file=sys.stderr)
        sys.exit(0)

    # Build and run simulation
    plugins = build_plugins(config)
    engine = SimulationEngine(config=config, plugins=plugins)

    try:
        results = engine.run()
    except Exception as e:
        print(f"Simulation error: {e}", file=sys.stderr)
        sys.exit(1)

    # Format output
    if args.format == "json":
        output = results_to_json(results)
    else:
        output = results_to_table(results)

    # Write output
    if args.output:
        args.output.write_text(output)
    else:
        print(output)


if __name__ == "__main__":
    main()
