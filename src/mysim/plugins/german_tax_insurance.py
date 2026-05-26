"""German tax and insurance plugin - progressive income tax, capital gains, GKV/PV."""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from mysim.config import AppConfig, EventConfig, GermanPluginConfig
from mysim.hooks import HookType
from mysim.plugin import Plugin
from mysim.state import LedgerEntry, SimulationState, ZERO

logger = logging.getLogger(__name__)

ONE = Decimal("1")
TWO = Decimal("2")


class GermanTaxInsurancePlugin(Plugin):
    """Calculates German income tax, capital gains tax, GKV, and PV."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config
        self._german_cfg = config.german_plugin_config
        self._events_by_year: dict[int, list[EventConfig]] = {}
        for event in config.events:
            if event.plugin == "german_tax_insurance":
                self._events_by_year.setdefault(event.year, []).append(event)

    def name(self) -> str:
        return "german_tax_insurance"

    def priority(self) -> int:
        return 0

    def hooks(self) -> list[HookType]:
        return [HookType.CALCULATE_TAX_AND_INSURANCE]

    def depends_on(self) -> list[str]:
        return ["pre_tax_summary"]

    def execute(self, state: SimulationState, hook: HookType) -> SimulationState:
        # Process status change events
        self._process_events(state)

        cfg = self._german_cfg

        # Calculate income tax on inflows (pensions, active income)
        taxable_income = self._compute_taxable_income(state)
        income_tax = self._calculate_progressive_income_tax(taxable_income, cfg)

        if income_tax > ZERO:
            state.deductions["income_tax"] = LedgerEntry(
                value=income_tax, label="Einkommensteuer"
            )

            # Church tax if applicable
            if cfg.confession_has_church_tax:
                church_tax = (income_tax * cfg.church_tax_rate).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                if church_tax > ZERO:
                    state.deductions["church_tax"] = LedgerEntry(
                        value=church_tax, label="Kirchensteuer"
                    )

        # Solidarity surcharge (Solidaritätszuschlag) - simplified
        soli = self._calculate_soli(income_tax)
        if soli > ZERO:
            state.deductions["solidarity_surcharge"] = LedgerEntry(
                value=soli, label="Solidaritätszuschlag"
            )

        # Capital gains tax (on realized gains only)
        # These are injected by the reconciliation plugin or other inflow sources
        # We also need to handle the German 'Teilfreistellung' (tax exemption)
        # and 'Sparer-Pauschbetrag'.
        cap_gains_tax = self._calculate_capital_gains_tax(state, cfg)
        if cap_gains_tax > ZERO:
            state.deductions["capital_gains_tax"] = LedgerEntry(
                value=cap_gains_tax, label="Abgeltungsteuer"
            )

        # Health insurance (GKV)
        gkv = self._calculate_gkv(state, cfg)
        if gkv > ZERO:
            state.deductions["gkv"] = LedgerEntry(
                value=gkv, label="Gesetzliche Krankenversicherung"
            )

        # Long-term care insurance (PV)
        pv = self._calculate_pv(state, cfg)
        if pv > ZERO:
            state.deductions["pv"] = LedgerEntry(
                value=pv, label="Pflegeversicherung"
            )

        # Add derivation trace if debug mode
        if state.debug:
            state.traces.append(self._build_trace(state, taxable_income, income_tax))

        return state

    def _process_events(self, state: SimulationState) -> None:
        """Process timeline events for this plugin."""
        if state.year in self._events_by_year:
            for event in self._events_by_year[state.year]:
                if event.action == "change_insurance_status":
                    new_status = event.parameters.get("health_insurance_status")
                    if new_status:
                        self._german_cfg.health_insurance_status = new_status

    def _compute_taxable_income(self, state: SimulationState) -> Decimal:
        """Compute total taxable income from inflows."""
        taxable = ZERO
        for key, entry in state.inflows.items():
            # Skip tax-free inflows (events marked as tax_free)
            if "tax_free" in key:
                continue
            taxable += entry.value
        return taxable

    def _calculate_progressive_income_tax(
        self, taxable_income: Decimal, cfg: GermanPluginConfig
    ) -> Decimal:
        """Calculate German progressive income tax using the 2024 formula approximation."""
        grundfreibetrag = cfg.grundfreibetrag
        is_married = cfg.income_tax_filing_status == "married"

        # Apply splitting for married (Zusammenveranlagung):
        # 1. Half the income
        # 2. Apply single Grundfreibetrag and progressive formula
        # 3. Double the resulting tax
        if is_married:
            splitting_income = taxable_income / TWO
        else:
            splitting_income = taxable_income

        # Effective taxable income after Grundfreibetrag
        effective_taxable = splitting_income - grundfreibetrag

        if effective_taxable <= ZERO:
            return ZERO

        # Progressive formula on the splitting income
        single_tax = self._progressive_formula(effective_taxable)

        if is_married:
            total_tax = single_tax * TWO
        else:
            total_tax = single_tax

        return total_tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _progressive_formula(self, zvE: Decimal) -> Decimal:
        """
        Simplified German income tax formula (2024 approximation).
        zvE = zu versteuerndes Einkommen (taxable income after Grundfreibetrag)
        
        Zone 1: 0 - 17,005 EUR -> 14% linear progressive to ~24%
        Zone 2: 17,006 - 66,760 EUR -> 24% linear progressive to 42%
        Zone 3: 66,761 - 277,825 EUR -> 42% flat
        Zone 4: > 277,825 EUR -> 45% flat
        """
        if zvE <= ZERO:
            return ZERO

        # Simplified bracket approximation
        zone1_limit = Decimal("17005")
        zone2_limit = Decimal("66760")
        zone3_limit = Decimal("277825")

        tax = ZERO

        if zvE <= zone1_limit:
            # ~14-24% progressive, approximate as average 19%
            tax = zvE * Decimal("0.19")
        elif zvE <= zone2_limit:
            # Tax on zone 1
            tax = zone1_limit * Decimal("0.19")
            # Zone 2: ~24-42% progressive, approximate as average 33%
            tax += (zvE - zone1_limit) * Decimal("0.33")
        elif zvE <= zone3_limit:
            tax = zone1_limit * Decimal("0.19")
            tax += (zone2_limit - zone1_limit) * Decimal("0.33")
            tax += (zvE - zone2_limit) * Decimal("0.42")
        else:
            tax = zone1_limit * Decimal("0.19")
            tax += (zone2_limit - zone1_limit) * Decimal("0.33")
            tax += (zone3_limit - zone2_limit) * Decimal("0.42")
            tax += (zvE - zone3_limit) * Decimal("0.45")

        return tax

    def _calculate_soli(self, income_tax: Decimal) -> Decimal:
        """Calculate Solidaritätszuschlag (5.5% of income tax above threshold)."""
        # Simplified: Soli is largely abolished for most taxpayers since 2021
        # Only applies above ~18,130 EUR income tax (single) / ~36,260 (married)
        threshold = Decimal("18130")
        if self._german_cfg.income_tax_filing_status == "married":
            threshold *= TWO

        if income_tax <= threshold:
            return ZERO

        soli = (income_tax - threshold) * Decimal("0.055")
        # Cap at 5.5% of full income tax
        max_soli = income_tax * Decimal("0.055")
        return min(soli, max_soli).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calculate_gkv(
        self, state: SimulationState, cfg: GermanPluginConfig
    ) -> Decimal:
        """Calculate GKV (statutory health insurance) contributions."""
        if cfg.health_insurance_status == "privat_versichert":
            return ZERO  # PKV handled separately (flat premium, out of scope)

        # Contribution base: total income capped at BBG
        income = state.total_inflows
        bbg = cfg.gkv_beitragsbemessungsgrenze_annual
        contribution_base = min(income, bbg)

        # Total rate: base rate + additional contribution
        total_rate = cfg.gkv_contribution_rate + cfg.gkv_additional_contribution

        # For freiwillig_versichert: full contribution (employer + employee share)
        # For pflichtversichert (KVdR): reduced rate on pensions
        if cfg.health_insurance_status == "pflichtversichert":
            # KVdR: only employee share (~half of total rate)
            gkv = contribution_base * (total_rate / TWO)
        else:
            # Freiwillig versichert: full rate
            gkv = contribution_base * total_rate

        return gkv.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calculate_capital_gains_tax(
        self, state: SimulationState, cfg: GermanPluginConfig
    ) -> Decimal:
        """Calculate German capital gains tax (Abgeltungsteuer)."""
        # Collect realized gains from inflows
        total_realized_gain = ZERO
        taxable_realized_gain = ZERO

        # We need to distinguish between equity funds (Teilfreistellung) and other gains
        # The reconcile plugin uses labels like "Realisierter Gewinn (Account Label)"
        # and keys like "realized_gain_account_key"

        # Track applied Sparer-Pauschbetrag
        remaining_pauschbetrag = cfg.sparer_pauschbetrag
        if cfg.income_tax_filing_status == "married":
            remaining_pauschbetrag *= TWO

        # Sort gains to apply pauschbetrag efficiently (though doesn't strictly matter for flat tax)
        # However, SRS says: "Apply sparer_pauschbetrag first to capital gains, then apply teilfreistellung on the remaining taxable amount."
        # This interaction is important.

        for key, entry in state.inflows.items():
            if not key.startswith("realized_gain_"):
                continue

            gain = entry.value
            if gain <= ZERO:
                continue

            # Check if this gain comes from an equity fund
            is_equity = False
            # Find the capital source by looking up the key suffix
            source_key = key[len("realized_gain_"):]
            if source_key in state.capital_sources:
                is_equity = state.capital_sources[source_key].is_equity_fund

            # 1. Apply Sparer-Pauschbetrag
            applicable_pausch = min(gain, remaining_pauschbetrag)
            gain_after_pausch = gain - applicable_pausch
            remaining_pauschbetrag -= applicable_pausch

            # 2. Apply Teilfreistellung for equity funds
            if is_equity and gain_after_pausch > ZERO:
                gain_after_pausch *= (ONE - cfg.stock_fund_tax_exempt_rate)

            taxable_realized_gain += gain_after_pausch

        if taxable_realized_gain <= ZERO:
            return ZERO

        # Apply flat tax rate (standard 25%)
        tax = taxable_realized_gain * cfg.fixed_capital_gains_tax_rate
        return tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _calculate_pv(
        self, state: SimulationState, cfg: GermanPluginConfig
    ) -> Decimal:
        """Calculate PV (long-term care insurance) contributions."""
        if cfg.health_insurance_status == "privat_versichert":
            return ZERO

        income = state.total_inflows
        bbg = cfg.gkv_beitragsbemessungsgrenze_annual
        contribution_base = min(income, bbg)

        # Base PV rate
        pv_rate = cfg.pv_base_rate

        # Childless surcharge
        if cfg.number_of_children == 0:
            pv_rate += cfg.pv_childless_surcharge

        # Child discount: -0.25% per child from child 2 onwards (max 5 children)
        if cfg.number_of_children >= 2:
            discount = min(cfg.number_of_children - 1, 4) * Decimal("0.0025")
            pv_rate -= discount

        pv = contribution_base * pv_rate
        return pv.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def _build_trace(
        self, state: SimulationState, taxable_income: Decimal, income_tax: Decimal
    ) -> dict[str, Any]:
        """Build a derivation trace for auditability."""
        return {
            "year": state.year,
            "deduction_type": "income_tax",
            "steps": [
                {
                    "step": "gross_income",
                    "value": str(state.total_inflows),
                    "source": "inflow_plugins",
                },
                {
                    "step": "grundfreibetrag",
                    "value": str(-self._german_cfg.grundfreibetrag),
                    "source": "german_tax_plugin",
                },
                {
                    "step": "taxable_income",
                    "value": str(taxable_income),
                    "source": "calculation",
                },
                {
                    "step": "progressive_tax",
                    "value": str(-income_tax),
                    "source": "german_tax_plugin",
                },
            ],
            "result": str(income_tax),
        }
