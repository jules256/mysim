
# Software Requirements Specification (SRS)
## Project: mysim (Core Simulation Model)

### 1. Vision & Abstract Lifecycle
The purpose of `mysim` is to build a highly decoupled financial simulation model that projects a single individual's financial situation across a multi-decade lifecycle. The simulation operates strictly on a **macro, discrete annual loop** (Year N calculates Year N+1). Mid-year, month-based, or day-based granularities are out of scope. The primary design goal is mathematical correctness, architectural modularity via plugins, and a strict decoupling of business logic from any presentational layers.

#### 1.1 Deterministic Execution
The simulation engine must produce byte-identical outputs for identical configuration inputs and engine versions. No implicit wall-clock time, locale, or non-seeded randomness may affect calculations. This ensures reproducibility for regression testing, scenario comparison, and result caching.

#### 1.2 Time Semantics
The simulation operates on a yearly basis, but ordering within the year is critical:
* **Inflation:** Applied at the beginning of the cycle to raw inputs.
* **Cashflow Reconciliation:** Occurs during the year to resolve inflows, outflows, and deductions.
* **Growth:** Asset growth compounds after annual cashflow reconciliation unless explicitly overridden by plugin logic.
* **Withdrawals:** Executed as part of cashflow reconciliation to cover shortfalls.

#### 1.3 Non-Goals & Disclaimers
* **Professional Advice:** The simulation provides planning-oriented approximations and does **not** constitute legal, tax, or financial advice.
* **Real-world Accuracy:** While aiming for correctness, the model simplifies certain real-world complexities to maintain its macro-level scope.

---

### 2. Core Technical Constraints
* **Language & Runtime:** Python 3.11 as an absolute minimal baseline version.
* **Target Environment:** Linux, specifically targeting Debian Trixie for development.
* **Security & Multi-Tenancy:** Out of scope. No user management, authentication, authorization, or network-level security models are required for the core model and initial UI iterations.
* **Performance Requirements:** Non-critical. The engine processes a single user's scenario sequence linearly; high-throughput concurrent parallel processing is not a requirement.
* **Localization Matrix:**
    * **Codebase Layer:** All variables, architectural patterns, schemas, class names, function names, and comments must be strictly in **English**.
    * **Presentation Layer:** All text labels, financial line-item descriptions, and table headers generated for export or user display must be strictly in **German**.
* **Numerical Precision:** All monetary calculations must use fixed-point decimal arithmetic (`Decimal`) rather than binary floating point. Internal precision must be maintained at a higher level than display precision. The standard rounding method is `ROUND_HALF_UP`.
* **Versioning Strategy:** The system must implement schema versioning for configurations and tax rule sets. A migration strategy must be defined to ensure backward compatibility as the engine and rule sets evolve.

---

### 3. Architecture & Plugin-Driven Topology
The architecture consists of a country-agnostic **Core Simulation Engine** that handles time-stepping and orchestration, and an **Event-Driven Hook System** where plugins inject country-specific or scenario-specific financial calculations.
* **Data Transparency Rule:** All plugins have open read-only access to all active values within the model state during execution.
* **Plugin Isolation Rules:** Plugins must interact with state via an explicit mutation API or domain ownership registry. Modifying attributes outside a plugin's specific domain is strictly prohibited to prevent tight coupling and debugging difficulties.

#### Event Conflict Resolution
Events scheduled for the same year execute deterministically in declaration order unless explicit plugin priorities override this behavior. The engine ensures a stable and predictable execution sequence for all concurrent event hooks.

#### Validation Layer
The engine must include a validation layer that fails fast on:
* **Invalid State Transitions:** e.g., impossible age jumps or inconsistent account totals.
* **Invariant Violations:** e.g., violation of the cost basis + growth = total rule.
* **Plugin Output Validation:** Ensuring plugin results conform to expected schemas and financial boundaries.

#### The Annual Lifecycle Pipeline (Hooks Sequence)
For every year in the simulation timeline, the Core Engine executes the following pipeline hooks in sequential order:

1. **`PRE_PROCESS`**: Plugins read/modify raw inputs, apply inflation increments, and process YAML scheduled timeline events.
2. **`PROCESS_INFLOWS`**: Inflow modules calculate gross active income, passive distributions, and pension milestones.
3. **`PROCESS_OUTFLOWS`**: Outflow modules calculate inflation-adjusted fixed living costs, variable spending, and target one-off expenses.
4. **`PRE_TAX_SUMMARY`**: A utility layer compiling aggregate gross financial lines before calculations of structural deductions.
5. **`CALCULATE_TAX_AND_INSURANCE`**: German Tax & Insurance modules hook in here to evaluate GKV, PV, and statutory progressive income tax ledgers.
6. **`RECONCILE_CASHFLOW`**: Balances net annual cash flows. Resolves shortfalls by pulling from designated accounts utilizing specific depot-level strategies (FIFO, pro-rata), or routes positive capital surpluses into compounding investment targets.
7. **`POST_PROCESS`**: Finalizes accounts by executing compound asset yield arithmetic (`capital_growth_rate`), pushing newly generated growth into the specialized accumulated yield tracking fields.

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
    * *Invariance Rule:* `capital_total` must always mathematically equal `capital_cost_basis + capital_growth_accumulated`.
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
* **Withdrawals:** Must follow a defined priority (e.g., principal-first vs. gain-first) based on the asset's liquidation strategy.

#### 4.2 Simulation Boundary Semantics
The engine must handle edge-case financial states:
* **Negative Capital:** Define whether negative balances are allowed (as debt) or if they mark the scenario as invalid/insolvent.
* **Insolvency:** If liquidity is insufficient to cover mandatory outflows/deductions, the engine must trigger a configurable policy (e.g., stop simulation, mark scenario as failed).

---

### 5. Specialized Plugin Logic Requirements (Germany Spec)
The system must support a dedicated German Tax and Insurance plugin parsing specialized tax rules:
* **Historical Rule Sets:** Tax and insurance plugins must support year-dependent rule evaluation to reflect historical and future changes in German tax law.
* **Filing Status Matrix:** Must compute using *Einzelveranlagung* (Single) or *Zusammenveranlagung* (Married), doubling brackets and standard tax-free allowances under the splitting methodology.
* **Tax Deductions & Reliefs:** Honor `grundfreibetrag` and `sparer_pauschbetrag` boundaries. Support optional Church Tax (*Kirchensteuer*) options.
* **Teilfreistellung Integration:** Support a fixed 30% tax-exemption rate on capital realizations originating from designated equity funds (*Aktienfonds*), calculation-isolated to the growth component.
* **Health & Long-Term Care Insurance System (GKV/PV/PKV):**
    * Evaluate health status across three clean dimensions: `pflichtversichert`, `freiwillig_versichert`, or `privat_versichert`.
    * Model the contribution ceilings (*Beitragsbemessungsgrenzen*).
    * Process a historical compliance check (`past_states`) simulating the **9/10 Rule** to verify eligibility for the *Krankenversicherung der Rentner (KVdR)* upon reaching statutory pension milestones. Include child-count offsets affecting *Pflegeversicherung* calculations.

---

### 6. Configuration Schema (Target YAML Blueprint)
This blueprint details how the parameters and dynamic override sequences pass parameters directly down to the pipeline hooks.

```yaml
# Configuration File Blueprint for "mysim"

simulation:
  birth_year: 1974
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
Calculated states remain entirely transient within in-memory structures during operation. On completion of the simulation timeline execution, the dataset must pass to presentation output buffers formatting the structured results directly as a flat temporal matrix. This matrix is consumed directly by future UI adapters or written to non-persistent physical structures via simple CSV or JSON pipelines.

#### 7.1 Auditability & Explainability
Each calculated deduction, tax result, or reconciliation step must optionally expose a structured derivation trace. This trace provides visibility into the reasoning and intermediate steps of complex calculations for debugging and audit purposes.

#### 7.2 Logging & Debug Mode
The engine must support a specialized debug mode including:
* **Trace Mode:** Detailed execution logs of pipeline hooks and plugin interactions.
* **Yearly Snapshots:** Full state captures at the end of each annual cycle.
* **Plugin Debug Hooks:** Hooks allowing plugins to inject custom debug information into the derivation trace.

#### 7.3 Scenario Comparison Support
The architecture must anticipate and support:
* **Batch Runs:** Efficient execution of multiple scenario variations.
* **Diffable Outputs:** Output formats that facilitate clear comparisons between different simulation runs (e.g., comparing retirement ages or inflation assumptions).


---

### 8. Testability Requirements
To ensure the integrity of the financial simulation, the following testing strategies are mandatory:
* **Golden Test Scenarios:** A suite of comprehensive, hand-verified "golden" scenarios used as benchmarks for correctness.
* **Deterministic Regression Tests:** Automated tests ensuring that engine changes do not alter outputs for identical configurations.
* **Invariant Tests:** Continuous validation of financial invariants (e.g., `capital_total == cost_basis + growth`) across all simulated years.
* **Snapshot Testing:** Comparison of full yearly state snapshots against known good baselines to detect subtle calculation drifts.
