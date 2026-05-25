"""CLI entry point for the mysim web UI."""

from __future__ import annotations

import argparse

from mysim.web.app import create_app


def main() -> None:
    """Run the mysim web server."""
    parser = argparse.ArgumentParser(description="mysim Web UI")
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port", type=int, default=5000, help="Port to listen on (default: 5000)"
    )
    parser.add_argument(
        "--scenarios", default="./scenarios", help="Path to scenarios directory"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable Flask debug mode"
    )

    args = parser.parse_args()

    app = create_app(scenarios_dir=args.scenarios)
    app.run(host=args.host, port=args.port, debug=args.debug)


if __name__ == "__main__":
    main()
