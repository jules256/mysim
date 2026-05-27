"""Configuration schema with Pydantic validation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class CapitalSourceConfig(BaseModel):
    """Configuration for a single capital account."""

    label: str
    capital_total: Decimal
    capital_cost_basis: Decimal
    capital_growth_accumulated: Decimal
    capital_growth_rate: Decimal = Field(ge=Decimal("-1"))
    withdrawal_strategy: Literal["fifo", "pro-rata", "gain-first"] = "pro-rata"
    is_equity_fund: bool = False

    @model_validator(mode="after")
    def validate_invariant(self) -> "CapitalSourceConfig":
        expected = self.capital_cost_basis + self.capital_growth_accumulated
        if abs(self.capital_total - expected) > Decimal("0.01"):
            raise ValueError(
                f"capital_total ({self.capital_total}) must equal "
                f"capital_cost_basis + capital_growth_accumulated ({expected})"
            )
        return self


class PensionConfig(BaseModel):
    """Configuration for a pension income stream."""

    name: str
    label: str
    amount: Decimal
    start_year: int
    yearly_increase_rate: Decimal = Decimal("0")


class GenericTrackersConfig(BaseModel):
    """Generic financial trackers."""

    fixed_costs_living: Decimal = Decimal("0")
    pocket_money: Decimal = Decimal("0")
    pensions: list[PensionConfig] = Field(default_factory=list)


class GermanPluginConfig(BaseModel):
    """German tax and insurance plugin configuration."""

    income_tax_filing_status: Literal["single", "married"] = "single"
    confession_has_church_tax: bool = False
    church_tax_rate: Decimal = Decimal("0.09")
    number_of_children: int = 0
    stock_fund_tax_exempt_rate: Decimal = Decimal("0.30")
    fixed_capital_gains_tax_rate: Decimal = Decimal("0.25")
    sparer_pauschbetrag: Decimal = Decimal("2000")
    grundfreibetrag: Decimal = Decimal("23456")
    health_insurance_status: Literal[
        "pflichtversichert", "freiwillig_versichert", "privat_versichert"
    ] = "pflichtversichert"
    kvdr_9_10_rule_fulfilled: bool = False
    gkv_contribution_rate: Decimal = Decimal("0.146")
    gkv_additional_contribution: Decimal = Decimal("0.017")
    gkv_beitragsbemessungsgrenze_annual: Decimal = Decimal("62100")
    pv_base_rate: Decimal = Decimal("0.0340")
    pv_childless_surcharge: Decimal = Decimal("0.006")


class EventConfig(BaseModel):
    """Configuration for a scheduled timeline event."""

    year: int
    label: str
    plugin: str
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class SimulationConfig(BaseModel):
    """Top-level simulation parameters."""

    birth_year: int
    start_year: int | None = None
    end_year: int | None = None
    baseline_inflation_rate: Decimal = Field(default=Decimal("0.02"), ge=Decimal("0"))
    capital_withdrawal_order: list[str] = Field(default_factory=list)
    insolvency_policy: Literal["stop", "debt"] = "stop"
    allow_negative_capital: bool = False
    debug: bool = False

    @model_validator(mode="after")
    def validate_years(self) -> "SimulationConfig":
        if self.start_year and self.end_year:
            if self.end_year <= self.start_year:
                raise ValueError("end_year must be greater than start_year")
        return self


class AppConfig(BaseModel):
    """Root configuration schema."""

    schema_version: int = 1
    engine_version: str = "0.1"
    simulation: SimulationConfig
    capital_sources: dict[str, CapitalSourceConfig] = Field(default_factory=dict)
    generic_trackers: GenericTrackersConfig = Field(default_factory=GenericTrackersConfig)
    german_plugin_config: GermanPluginConfig = Field(default_factory=GermanPluginConfig)
    events: list[EventConfig] = Field(default_factory=list)
