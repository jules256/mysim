"""Output formatting - temporal matrix and structured results."""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any


class DecimalEncoder(json.JSONEncoder):
    """JSON encoder that handles Decimal values."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Decimal):
            return str(obj)
        return super().default(obj)


def results_to_json(results: list[dict[str, Any]], indent: int = 2) -> str:
    """Convert simulation results to JSON string."""
    return json.dumps(results, cls=DecimalEncoder, indent=indent)


def results_to_table(results: list[dict[str, Any]]) -> str:
    """Format results as a readable text table."""
    if not results:
        return "No results."

    # Standard columns
    columns = [
        ("year", "Jahr", 6),
        ("age", "Alter", 6),
        ("total_inflows", "Zuflüsse", 14),
        ("total_outflows", "Abflüsse", 14),
        ("total_deductions", "Abzüge", 14),
        ("net_annual_result", "Netto", 14),
    ]

    # Detect capital columns dynamically
    capital_cols = sorted(
        [k for k in results[0].keys() if k.startswith("capital_total_")]
    )
    for col in capital_cols:
        label = col.replace("capital_total_", "Kapital ")
        columns.append((col, label, 16))

    # Header
    header = " | ".join(f"{label:>{width}}" for _, label, width in columns)
    separator = "-+-".join("-" * width for _, _, width in columns)

    lines = [header, separator]

    for row in results:
        values = []
        for key, _, width in columns:
            val = row.get(key, "")
            if isinstance(val, Decimal):
                val = f"{val:,.2f}"
            values.append(f"{val:>{width}}")
        lines.append(" | ".join(values))

    return "\n".join(lines)
