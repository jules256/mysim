"""Jinja2 template filters for German locale formatting."""

from __future__ import annotations

from decimal import Decimal

from flask import Flask


def format_german_currency(value) -> str:
    """Format a decimal value as German currency: 1.234,56 €."""
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = Decimal(value)
        except Exception:
            return value

    if not isinstance(value, (Decimal, int, float)):
        return str(value)

    value = Decimal(str(value))
    is_negative = value < 0
    abs_val = abs(value)

    # Format with 2 decimal places
    formatted = f"{abs_val:,.2f}"
    # Swap separators for German locale: 1,234.56 -> 1.234,56
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    if is_negative:
        return f"-{formatted} €"
    return f"{formatted} €"


def format_german_number(value) -> str:
    """Format a number with German locale separators."""
    if value is None:
        return "—"
    if isinstance(value, str):
        try:
            value = Decimal(value)
        except Exception:
            return value

    if isinstance(value, bool):
        return "Ja" if value else "Nein"

    if isinstance(value, int):
        formatted = f"{value:,}".replace(",", ".")
        return formatted

    value = Decimal(str(value))
    formatted = f"{value:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return formatted


def register_filters(app: Flask) -> None:
    """Register custom Jinja2 filters."""
    app.jinja_env.filters["german_currency"] = format_german_currency
    app.jinja_env.filters["german_number"] = format_german_number
