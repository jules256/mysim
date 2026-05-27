from decimal import Decimal

import pytest

from mysim.config import AppConfig, CapitalSourceConfig, SimulationConfig
from mysim.state import CapitalSource, LedgerEntry, SimulationState
from mysim.validation import ValidationError, validate_state


def _base_state() -> SimulationState:
    return SimulationState(
        year=2026,
        age=52,
        start_year=2026,
        inflation_rate=Decimal("0.02"),
        capital_sources={
            "savings": CapitalSource(
                label="Sparkonto",
                capital_total=Decimal("100000"),
                capital_cost_basis=Decimal("100000"),
                capital_growth_accumulated=Decimal("0"),
                capital_growth_rate=Decimal("0"),
                withdrawal_strategy="pro-rata",
                is_equity_fund=False,
            )
        },
        inflows={
            "salary": LedgerEntry(value=Decimal("50000"), label="Gehalt")
        },
        outflows={
            "costs": LedgerEntry(value=Decimal("25000"), label="Lebenshaltungskosten")
        },
        deductions={},
        capital_withdrawal_order=["savings"],
    )


def test_invalid_end_year_raises():
    with pytest.raises(ValueError, match="end_year must be greater than start_year"):
        SimulationConfig(birth_year=1974, start_year=2030, end_year=2029)


def test_capital_source_config_invariant_validation():
    with pytest.raises(ValueError, match="capital_total.*must equal"):
        CapitalSourceConfig(
            label="Depot",
            capital_total=Decimal("1000"),
            capital_cost_basis=Decimal("900"),
            capital_growth_accumulated=Decimal("50"),
            capital_growth_rate=Decimal("0.03"),
        )


def test_state_round_decimal_and_invariant_enforcement():
    state = _base_state()
    assert state.round_decimal(Decimal("123.456")) == Decimal("123.46")

    source = state.capital_sources["savings"]
    source.capital_total = Decimal("100000.005")
    source.capital_cost_basis = Decimal("100000")
    source.capital_growth_accumulated = Decimal("0")
    source.enforce_invariant()
    assert source.capital_growth_accumulated == Decimal("0.005")


def test_validate_state_auto_corrects_small_discrepancy():
    state = _base_state()
    source = state.capital_sources["savings"]
    source.capital_total = Decimal("100000.009")
    source.capital_cost_basis = Decimal("100000")
    source.capital_growth_accumulated = Decimal("0")

    validate_state(state)
    assert source.capital_growth_accumulated == Decimal("0.009")


def test_validate_state_rejects_negative_capital():
    state = _base_state()
    source = state.capital_sources["savings"]
    source.capital_total = Decimal("-1")
    source.capital_cost_basis = Decimal("0")
    source.capital_growth_accumulated = Decimal("-1")

    with pytest.raises(ValidationError, match="Negative capital detected"):
        validate_state(state)


def test_validate_state_allows_negative_capital_when_configured():
    state = _base_state()
    state.allow_negative_capital = True
    source = state.capital_sources["savings"]
    source.capital_total = Decimal("-1")
    source.capital_cost_basis = Decimal("0")
    source.capital_growth_accumulated = Decimal("-1")

    validate_state(state)
