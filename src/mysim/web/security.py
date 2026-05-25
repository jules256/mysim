"""Security and validation helpers."""

from __future__ import annotations

import re
import time
from collections import defaultdict
from functools import wraps

from flask import abort, current_app, request

# Scenario name validation
SCENARIO_NAME_PATTERN = re.compile(r"^[a-z0-9_-]+$")
MAX_SCENARIO_NAME_LENGTH = 64

# Simple in-memory rate limiter
_rate_store: dict[str, list[float]] = defaultdict(list)


def validate_scenario_name(name: str) -> str:
    """Validate and sanitize a scenario name. Aborts with 404 on invalid input."""
    if not name or len(name) > MAX_SCENARIO_NAME_LENGTH:
        abort(404, description=f"Scenario '{name}' does not exist.")
    if not SCENARIO_NAME_PATTERN.match(name):
        abort(404, description=f"Scenario '{name}' does not exist.")
    return name


def check_rate_limit() -> None:
    """Check rate limit for simulation executions. Aborts with 429 if exceeded."""
    max_requests = current_app.config.get("RATE_LIMIT_MAX", 10)
    client_ip = request.remote_addr or "unknown"
    now = time.time()

    # Clean old entries (older than 60 seconds)
    _rate_store[client_ip] = [
        t for t in _rate_store[client_ip] if now - t < 60
    ]

    if len(_rate_store[client_ip]) >= max_requests:
        abort(429, description="Rate limit exceeded. Maximum 10 simulations per minute.")

    _rate_store[client_ip].append(now)


def rate_limited(f):
    """Decorator to apply rate limiting to a route."""
    @wraps(f)
    def decorated(*args, **kwargs):
        check_rate_limit()
        return f(*args, **kwargs)
    return decorated
