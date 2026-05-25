
# Software Requirements Specification (SRS)
## Project: mysim (Core Simulation Model)

### 1. Vision & Abstract Lifecycle
The purpose of `mysim` is to build a highly decoupled financial simulation model that projects a single individual's financial situation across a multi-decade lifecycle. The simulation operates strictly on a **macro, discrete annual loop** (Year N calculates Year N+1). Mid-year, month-based, or day-based granularities are out of scope. The primary design goal is mathematical correctness, architectural modularity via plugins, and a strict decoupling of business logic from any presentational layers.

#### 1.1 Deterministic Execution
The simulation engine must produce numerically identical structured outputs (or deterministic normalized outputs) for identical configuration inputs and engine versions. No implicit wall-clock time, locale, or non-seeded randomness may affect calculations. This ensures reproducibility for regression testing, scenario comparison, and result caching.

#### 1.2 Time Semantics
The simulation operates on a yearly basis, but ordering within the year is critical to ensure mathematical consistency:
1. **Inflation:** Applied at the beginning of the cycle to raw inputs and recurring financial trackers.
2. **Cashflow Operations:** Resolution of annual inflows, outflows, and mandatory deductions (taxes/insurance).
3. **Growth:** Asset growth compounds based on the state *after* primary cashflow resolution but *before* final shortfall withdrawals.
4. **Withdrawals:** Executed at the end of the cycle to cover any remaining cashflow shortfalls, drawing from grown assets.

#### 1.3 Non-Goals & Disclaimers
* **Professional Advice:** The simulation provides planning-oriented approximations and does **not** constitute legal, tax, or financial advice.
* **Real-world Accuracy:** While aiming for correctness, the model simplifies certain real-world complexities to maintain its macro-level scope.

#### 1.4 Intended Abstraction Level
The `mysim` engine is primarily intended as a **retirement planning approximation** tool. While the architecture is designed to support the precision required for a tax-accurate simulation engine, the current model prioritizes macro-level trajectory forecasting over transaction-level ledger accuracy.

#### 1.5 Future Extensions
Probabilistic or stochastic simulation modes (e.g., Monte Carlo runs, sequence-of-return risk modeling) are considered future extensions and are not part of the initial deterministic baseline engine.

---

### 2. Core Technical Constraints
* **Language & Runtime:** Python 3.11 as an absolute minimal baseline version.
* **Target Environment:** Linux, specifically targeting Debian Trixie for development.
* **Security & Multi-Tenancy:** Out of scope. No user management, authentication, authorization, or network-level security models are required for the core model and initial UI iterations.
* **Performance Requirements:** Non-critical. The engine processes a single user's scenario sequence linearly; high-throughput concurrent parallel processing is not a requirement. A simulation of 50 years with 10 accounts and 5 plugins must complete in <1 second on a modern CPU.
* **Localization Matrix:**
    * **Codebase Layer:** All variables, architectural patterns, schemas, class names, function names, and comments must be strictly in **English**.
    * **Presentation Layer:** All text labels, financial line-item descriptions, and table headers generated for export or user display must be strictly in **German**.
* **Numerical Precision:** All monetary calculations must use fixed-point decimal arithmetic (`Decimal`) rather than binary floating point. Internal precision must be maintained at a higher level than display precision. The standard rounding method is `ROUND_HALF_UP`.
* **Versioning Strategy:** The system must implement schema versioning for configurations and tax rule sets. A migration strategy must be defined to ensure backward compatibility as the engine and rule sets evolve.
    * **Backward-compatible changes:** Auto-migrate (e.g., new optional fields).
    * **Breaking changes:** Require explicit `schema_version` bump + migration script (e.g., `schema_version: 2` if `capital_growth_rate` now mandatory).
* **Currency Semantics:** The engine assumes a single-currency environment (defaulting to EUR). Multi-currency support and FX-rate modeling are intentionally excluded from the current architectural scope.

---

### 3. Architecture & Plugin-Driven Topology
The architecture consists of a country-agnostic **Core Simulation Engine** that handles time-stepping and orchestration, and an **Event-Driven Hook System** where plugins inject country-specific or scenario-specific financial calculations.
* **Separation of Engine & Rules:** The core engine must contain zero country-specific constants. All regulatory parameters and tax rules must be externalized via plugins or configuration sets.
* **Data Transparency Rule:** All plugins have open read-only access to all active values within the model state during execution.
* **Plugin Isolation Rules:** Plugins must interact with state via an explicit mutation API or domain ownership registry. Modifying attributes outside a plugin's specific domain is strictly prohibited to prevent tight coupling and debugging difficulties.

#### Event Conflict Resolution & Plugin Ordering
The engine ensures a stable and predictable execution sequence for all concurrent event hooks:
1. **Priority:** Plugins and events declare a `priority: int` (default: 0). Lower values execute first.
2. **Dependencies:** Plugins may explicitly declare a dependency graph (e.g., `depends_on: ["german_tax"]`).
3. **Deterministic Tie-breaking:** Conflicts with identical priorities are resolved by declaration order in the configuration.

#### Plugin Interface Contract
To ensure discoverability and validation, all plugins must adhere to a standardized interface:
```python
class Plugin(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def priority(self) -> int: (default: 0)

    @abstractmethod
    def hooks(self) -> List[HookType]: (e.g., [PRE_PROCESS, CALCULATE_TAX])

    @abstractmethod
    def execute(self, state: SimulationState, hook: HookType) -> SimulationState: ...
```

#### Validation Layer
The engine must include a validation layer implementing a **"Fail Loudly and Early"** philosophy. The engine supports a configurable `error_policy`: `strict` (default, abort on errors) or `warn_and_continue` (log but proceed for debugging edge cases). The system must abort execution immediately (in `strict` mode) upon detecting:
* **Invalid State Transitions:** e.g., impossible age jumps or inconsistent account totals.
* **Invariant Violations:** e.g., violation of the cost basis + growth = total rule.
* **Plugin Output Validation:** Ensuring plugin results conform to expected schemas and financial boundaries.
* **Unknown Event Types:** Detection of undefined or unrecognized events in the configuration.
* **Rounding Mismatches:** Significant discrepancies during invariant checks caused by rounding errors.
* **Configuration Gaps:** Missing mandatory plugin fields or configuration parameters.

#### The Annual Lifecycle Pipeline (Hooks Sequence)
For every year in the simulation timeline, the Core Engine executes the following pipeline hooks in sequential order:

1. **`PRE_PROCESS`**: Plugins read/modify raw inputs, apply inflation increments, and process YAML scheduled timeline events.
2. **`PROCESS_INFLOWS`**: Inflow modules calculate gross active income, passive distributions, and pension milestones.
3. **`PROCESS_OUTFLOWS`**: Outflow modules calculate inflation-adjusted fixed living costs, variable spending, and target one-off expenses.
4. **`PRE_TAX_SUMMARY`**: A utility layer compiling aggregate gross financial lines before calculations of structural deductions.
5. **`CALCULATE_TAX_AND_INSURANCE`**: German Tax & Insurance modules hook in here to evaluate GKV, PV, and statutory progressive income tax ledgers.
6. **`POST_PROCESS`**: Executes compound asset yield arithmetic (`capital_growth_rate`) on the current state. Newly generated growth is pushed into the `capital_growth_accumulated` fields.
7. **`RECONCILE_CASHFLOW`**: Balances net annual cash flows. Resolves shortfalls by pulling from grown designated accounts utilizing specific depot-level strategies (FIFO, pro-rata), or routes positive capital surpluses into compounding investment targets.

---

### 4. Data Layer & State Management (`SimulationState`)
The core data container travels dynamically through the pipeline. It stores absolute state for the active year and tracks capital cost bases separately from compounding growth.

#### Data Schema
* **Global Metadata:**
    * `year` (`int`): Active calendar year.
    * `age` (`int`): Current age of the user.
    * `inflation_rate` (`Decimal`): Active annual inflation coefficient.
* **Capital Accounts Portfolio (`capital_sources`):**
    * A key-value dictionary map storing distinct isolated account/depot entities:
        * `label` (`str`): German presentation string (e.g., *"Comdirect Kern-Depot"*).
        * `capital_total` (`Decimal`): Total current evaluation of the source asset.
        * `capital_cost_basis` (`Decimal`): The original principal injected money portion.
        * `capital_growth_accumulated` (`Decimal`): Accumulated unrealized yield portion.
        * `capital_growth_rate` (`Decimal`): Individual expected compound return factor.
        * `withdrawal_strategy` (`str`): Strategy used upon asset liquidation (e.g., `fifo`, `pro-rata`).
    * *Invariance Rule & Tolerance:* `capital_total` must always mathematically equal `capital_cost_basis + capital_growth_accumulated`. A rounding tolerance of `0.01` is allowed. If a discrepancy exists within this threshold, the engine must automatically adjust `capital_growth_accumulated` to enforce the invariant. Discrepancies exceeding this threshold must trigger a fatal error.
* **Dynamic Maps (Financial Ledger Units):**
    * Every map entry contains a structured payload: `{"value": Decimal, "label": str}` where the label is in German.
    * `inflows`: Aggregates active incomes and gross asset realizations.
    * `outflows`: Aggregates inflation-adjusted living costs and target investments.
    * `deductions`: Aggregates mandatory regulatory fees (Income Taxes, Capital Gains Taxes, GKV, PV).
* **Summary Metrics:**
    * `total_inflows`, `total_outflows`, `total_deductions`
    * `net_annual_result`: `total_inflows - total_outflows - total_deductions`.

#### 4.1 Accounting Semantics
The engine must explicitly define the treatment of various financial flows:
* **Realized Gains:** Treated as `inflows` within a dedicated sub-ledger purely as a calculation base for taxes and GKV. They do **not** count as "new external cash" injected into the system, as the capital already exists within the asset pool. This prevents double-counting during cashflow reconciliation.
* **Taxes & Insurance:** All regulatory liabilities (including progressive income tax, capital gains tax withheld at source, and health/long-term care insurance) are strictly standardized under the `deductions` ledger. This ensures a uniform code footprint and reconciliation logic, regardless of whether the liability is withheld at the source or paid in arrears.
* **Transfers:** Transfers between accounts do not count as net inflows/outflows but must be tracked for cost-basis adjustments.
* **Growth:** Unrealized growth is tracked separately and is only taxable upon realization (e.g., withdrawal).
* **Withdrawal Strategies:**
    * `fifo`: Withdraw from the oldest units first. Requires tracking of individual tax lots (see Section 4.4).
    * `pro-rata`: Withdraw proportionally from the cost basis and the accumulated growth (e.g., a 10% withdrawal pulls 10% from basis and 10% from growth).
    * `gain-first`: Withdraw from accumulated growth first, preserving the cost basis as long as possible (often used for tax-optimization simulations).

#### 4.2 Simulation Boundary Semantics
The engine must handle edge-case financial states using a strict policy set:
* **Negative Capital:** By default, negative capital is not allowed. The engine treats any account dropping below zero as an insolvency event unless an explicit `allow_negative_capital: true` override is provided in the configuration.
* **Insolvency Policies:** If annual liquidity is insufficient to cover mandatory outflows/deductions, the engine triggers one of the following configurable policies:
    * `stop` (Default): Halt the simulation immediately and mark the scenario as failed.
    * `debt`: Allow the simulation to continue by tracking the shortfall as a negative balance (debt liability).

#### 4.3 Economic, Cash, and Tax Ledger Views
To simplify future complexity, the engine formalizes the separation between different financial perspectives, even if implemented as internal views:
* **Economic Ledger:** Tracks theoretical growth and value appreciation regardless of realization.
* **Cash Ledger:** Tracks actual movement of liquid funds (inflows, outflows, and net results).
* **Taxable Ledger:** Tracks realized gains and other taxable events that trigger regulatory deductions.

#### 4.4 Asset Lot Modeling (Future Scaling)
While aggregate tracking of `capital_cost_basis` and `capital_growth_accumulated` is sufficient for high-level approximations, accurate FIFO taxation will eventually require a transition to **tax lot modeling**.

**Evolution Roadmap:**
* **Phase 1 (Current):** Aggregate tracking at the account level.
* **Phase 2 (Future):** Full lot modeling where assets are represented as a collection of `TaxLot` objects:
    * `acquisition_year`: The year of purchase.
    * `principal`: The cost basis for the specific lot.
    * `growth`: The accumulated growth for the specific lot.
    * `asset_class`: The classification (e.g., *Aktienfonds*) for specific tax treatment.

**Migration Path:** Future versions will introduce a `tax_lot_mode: bool` flag to toggle between aggregate and granular lot tracking.

---

### 5. Specialized Plugin Logic Requirements (Germany Spec)
The system must support a dedicated German Tax and Insurance plugin parsing specialized tax rules:
* **Historical Rule Sets:** Tax and insurance plugins must support year-dependent rule evaluation to reflect historical and future changes in German tax law.
* **Filing Status Matrix:** Must compute using *Einzelveranlagung* (Single) or *Zusammenveranlagung* (Married), doubling brackets and standard tax-free allowances under the splitting methodology.
* **Tax Deductions & Reliefs:**
    * Honor `grundfreibetrag` and `sparer_pauschbetrag` boundaries.
    * **Interaction:** Apply `sparer_pauschbetrag` first to capital gains, then apply `teilfreistellung` on the remaining taxable amount.
    * Support optional Church Tax (*Kirchensteuer*) via a configurable `church_tax_rate` (typically 8-9% of the income tax).
* **Teilfreistellung Integration:** Support a fixed 30% tax-exemption rate on capital realizations originating from designated equity funds (*Aktienfonds*), calculation-isolated to the growth component.
* **Health & Long-Term Care Insurance System (GKV/PV/PKV):**
    * Evaluate health status across three clean dimensions: `pflichtversichert`, `freiwillig_versichert`, or `privat_versichert`.
    * Model the contribution ceilings (*Beitragsbemessungsgrenzen*).
    * **9/10 Rule for KVdR:** To verify eligibility for *Krankenversicherung der Rentner (KVdR)*, the engine must track `past_states` from age 16. Eligibility requires that at least 90% of the time between age 16 and statutory pension age was spent under a `pflichtversichert` status.
    * Include child-count offsets affecting *Pflegeversicherung* calculations.

---

### 6. Configuration Schema (Target YAML Blueprint)
This blueprint details how parameters pass to the pipeline hooks. The engine must validate configurations against a strict schema (e.g., Pydantic) ensuring:
* **Required Fields:** e.g., `birth_year`, `capital_sources`.
* **Value Constraints:** e.g., `inflation_rate >= 0`, `capital_growth_rate >= -1`.
* **Cross-field Validation:** e.g., `end_year > start_year`.

```yaml
# Configuration File Blueprint for "mysim"
schema_version: 1
engine_version: "0.1"

simulation:
  birth_year: 1974
  error_policy: "strict"  # or "warn_and_continue"
  # Optional manual overrides (Defaults to current_year -> age 100 if omitted)
  start_year: 2026
  end_year: 2074
  baseline_inflation_rate: 0.02
  capital_withdrawal_order:
    - "tagesgeld"
    - "depot_trade_republic"
    - "depot_comdirect"

capital_sources:
  tagesgeld:
    label: "Tagesgeld Reserve"
    capital_total: 50000.0
    capital_cost_basis: 50000.0
    capital_growth_accumulated: 0.0
    capital_growth_rate: 0.02
    withdrawal_strategy: "pro-rata"
  depot_trade_republic:
    label: "Trade Republic Depot"
    capital_total: 150000.0
    capital_cost_basis: 110000.0
    capital_growth_accumulated: 40000.0
    capital_growth_rate: 0.04
    withdrawal_strategy: "fifo"
  depot_comdirect:
    label: "Comdirect Kern-Depot"
    capital_total: 300000.0
    capital_cost_basis: 150000.0
    capital_growth_accumulated: 150000.0
    capital_growth_rate: 0.05
    withdrawal_strategy: "fifo"

generic_trackers:
  fixed_costs_living: 24000.0
  pocket_money: 6000.0
  pensions:
    - name: "gesetzliche_rente"
      label: "Gesetzliche Rente (DRV)"
      amount: 21600.0
      start_year: 2041
      yearly_increase_rate: 0.01

german_plugin_config:
  income_tax_filing_status: "married"
  confession_has_church_tax: true
  number_of_children: 0
  stock_fund_tax_exempt_rate: 0.30
  fixed_capital_gains_tax_rate: 0.25
  sparer_pauschbetrag: 2000.0
  grundfreibetrag: 23456.0
  health_insurance_status: "freiwillig_versichert"
  kvdr_9_10_rule_fulfilled: true
  gkv_contribution_rate: 0.146
  gkv_additional_contribution: 0.017
  gkv_beitragsbemessungsgrenze_annual: 62100.0

events:
  - year: 2030
    label: "Erbschaft"
    plugin: "inflow_tracker"
    action: "one_time_inflow"
    parameters:
      amount: 50000.0
      type: "tax_free"

  - year: 2035
    label: "Anpassung Inflation"
    plugin: "core_engine"
    action: "update_baseline"
    parameters:
      inflation_rate: 0.035

  - year: 2045
    label: "Statuswechsel KVdR"
    plugin: "german_tax_insurance"
    action: "change_insurance_status"
    parameters:
      health_insurance_status: "pflichtversichert"
```
---

### 7. Core Operational Output
Calculated states remain entirely transient within in-memory structures during operation. On completion of the simulation timeline execution, the dataset must pass to presentation output buffers formatting the structured results directly as a flat temporal matrix.

#### 7.1 Temporal Matrix Structure
The flat output matrix must include the following standard columns for every year:
| Column | Type | Description |
| :--- | :--- | :--- |
| `year` | `int` | Calendar year |
| `age` | `int` | User age |
| `total_inflows` | `Decimal` | Sum of all active/passive inflows |
| `total_outflows` | `Decimal` | Sum of all expenses and target investments |
| `total_deductions` | `Decimal` | Sum of taxes and social insurance |
| `net_annual_result` | `Decimal` | `inflows - outflows - deductions` |
| `capital_total_{account}` | `Decimal` | Total value per account entity |
| `deductions_{type}` | `Decimal` | Detailed breakdown per deduction line item |
| `is_insolvent` | `bool` | Flag indicating if an insolvency event occurred |

#### 7.2 Auditability & Explainability (Derivation Traces)
Each calculated deduction, tax result, or reconciliation step must optionally expose a structured derivation trace (JSON). This provides visibility for debugging and audit purposes.
**Example Trace:**
```json
{
  "year": 2030,
  "deduction_type": "income_tax",
  "steps": [
    {"step": "gross_income", "value": 50000, "source": "pension_plugin"},
    {"step": "grundfreibetrag", "value": -23456, "source": "german_tax_plugin"},
    {"step": "taxable_income", "value": 26544, "source": "calculation"},
    {"step": "progressive_tax", "value": -4500, "source": "german_tax_plugin"}
  ],
  "result": 4500
}
```

#### 7.3 Logging & Debug Mode
The engine must support a specialized debug mode including:
* **Trace Mode:** Detailed execution logs of pipeline hooks and plugin interactions.
* **Yearly Snapshots:** Full state captures at the end of each annual cycle.
* **Plugin Debug Hooks:** Hooks allowing plugins to inject custom debug information into the derivation trace.

#### 7.4 Scenario Comparison Support
The architecture must anticipate and support:
* **Batch Runs:** Efficient execution of multiple scenario variations using parallel processing. This utilizes a `multiprocessing` approach (CPU-bound) with a configurable `max_workers` limit (defaulting to `os.cpu_count()`).
* **Diffable Outputs:** Output formats that facilitate clear comparisons between different simulation runs (e.g., comparing retirement ages or inflation assumptions).

#### 7.5 Operational Improvements
* **Dry Run Mode:** A `--dry-run` flag to validate configurations (required fields, plugin references, dependency loops) without executing the full simulation.
* **Checkpointing:** Support for saving and loading full simulation states (all accounts, ledgers, and metadata) at any year $N$ using JSON (human-readable) or MessagePack (compact) formats to facilitate debugging and partial re-runs.
* **Standardized Logging:**
    * **Levels:** `ERROR` (invariants/fatal), `WARN` (rounding/deprecation), `INFO` (milestones), `DEBUG` (full trace).
    * **Format:** Structured JSON format for machine-readability.


---

### 8. Testability Requirements
To ensure the integrity of the financial simulation, the following testing strategies are mandatory:
* **Golden Test Scenarios:** A suite of comprehensive, hand-verified "golden" scenarios used as benchmarks for correctness. Scenarios must include:
    * **Baseline Scenario:** Single account, zero inflation, zero taxes, simple constant growth.
    * **German Tax Scenario:** Progressive income tax, `grundfreibetrag`, `sparer_pauschbetrag`, and `teilfreistellung` interactions.
    * **Withdrawal Strategy Scenario:** Side-by-side comparison of `fifo`, `pro-rata`, and `gain-first` behaviors.
    * **Insolvency Scenario:** Verified trigger of `stop` and `debt` policies under liquidity shortfalls.
* **Deterministic Regression Tests:** Automated tests ensuring that engine changes do not alter outputs for identical configurations.
* **Invariant Tests:** Continuous validation of financial invariants (e.g., `capital_total == cost_basis + growth`) across all simulated years.
* **Snapshot Testing:** Comparison of full yearly state snapshots against known good baselines to detect subtle calculation drifts.
