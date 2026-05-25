"""Flask application factory and configuration."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from flask import Flask

from mysim.web.routes import bp
from mysim.web.filters import register_filters


def create_app(scenarios_dir: str | None = None) -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=str(Path(__file__).parent / "static"),
    )

    # Configuration
    app.config["SCENARIOS_DIR"] = Path(
        scenarios_dir or os.environ.get("MYSIM_SCENARIOS_DIR", "./scenarios")
    ).resolve()
    app.config["MAX_YAML_SIZE"] = 1 * 1024 * 1024  # 1MB
    app.config["MAX_EXPORT_SIZE"] = 10 * 1024 * 1024  # 10MB
    app.config["EXPORT_DIR"] = Path("/tmp/mysim_exports")
    app.config["RATE_LIMIT_MAX"] = 10  # per minute
    app.config["SECRET_KEY"] = os.environ.get("MYSIM_SECRET_KEY", "dev-key-not-for-prod")

    # Ensure directories exist
    app.config["SCENARIOS_DIR"].mkdir(parents=True, exist_ok=True)
    app.config["EXPORT_DIR"].mkdir(parents=True, exist_ok=True)

    # Logging
    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)

    # Register blueprint
    app.register_blueprint(bp)

    # Register Jinja2 filters
    register_filters(app)

    return app
