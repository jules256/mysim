"""Simulation state data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


ZERO = Decimal("0")
ROUNDING_TOLERANCE = Decimal("0.01")


@dataclass
class LedgerEntry:
    """A single financial ledger line item."""

    value: Decimal
    label: str  # German presentation label
    is_tax_free: bool = False


@dataclass
class CapitalSource:
    """A single capital account/depot entity."""

    label: str
    capital_total: Decimal
    capital_cost_basis: Decimal
    capital_growth_accumulated: Decimal
    capital_growth_rate: Decimal
    withdrawal_strategy: str  # "fifo", "pro-rata", "gain-first"

    def enforce_invariant(self) -> None:
        """Enforce capital_total == capital_cost_basis + capital_growth_accumulated."""
        expected = self.capital_cost_basis + self.capital_growth_accumulated
        discrepancy = abs(self.capital_total - expected)
        if discrepancy > ROUNDING_TOLERANCE:
            raise ValueError(
                f"Capital invariant violation for '{self.label}': "
                f"total={self.capital_total}, basis={self.capital_cost_basis}, "
                f"growth={self.capital_growth_accumulated}, discrepancy={discrepancy}"
            )
        if discrepancy > ZERO:
            self.capital_growth_accumulated = self.capital_total - self.capital_cost_basis


@dataclass
class SimulationState:
    """Core data container traveling through the annual pipeline."""

    # Global metadata
    year: int
    age: int
    inflation_rate: Decimal

    # Capital accounts portfolio
    capital_sources: dict[str, CapitalSource] = field(default_factory=dict)

    # Financial ledger maps
    inflows: dict[str, LedgerEntry] = field(default_factory=dict)
    outflows: dict[str, LedgerEntry] = field(default_factory=dict)
    deductions: dict[str, LedgerEntry] = field(default_factory=dict)

    # Summary metrics (computed during pipeline)
    total_inflows: Decimal = ZERO
    total_outflows: Decimal = ZERO
    total_deductions: Decimal = ZERO
    net_annual_result: Decimal = ZERO

    # Insolvency flag
    is_insolvent: bool = False

    # Allow negative capital when explicitly enabled in configuration
    allow_negative_capital: bool = False

    # Derivation traces for auditability
    traces: list[dict[str, Any]] = field(default_factory=list)

    # Capital withdrawal order (account keys in priority)
    capital_withdrawal_order: list[str] = field(default_factory=list)

    # Debug mode flag
    debug: bool = False

    def compute_summaries(self) -> None:
        """Recompute summary totals from ledger maps."""
        self.total_inflows = sum(
            (e.value for e in self.inflows.values()), ZERO
        )
        self.total_outflows = sum(
            (e.value for e in self.outflows.values()), ZERO
        )
        self.total_deductions = sum(
            (e.value for e in self.deductions.values()), ZERO
        )
        self.net_annual_result = (
            self.total_inflows - self.total_outflows - self.total_deductions
        )

    def round_decimal(self, value: Decimal, places: int = 2) -> Decimal:
        """Round a decimal value to the given number of places using ROUND_HALF_UP."""
        quantize_str = Decimal(10) ** -places
        return value.quantize(quantize_str, rounding=ROUND_HALF_UP)
