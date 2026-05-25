
# Software Requirements Specification (SRS)
## Project: mysim (Web UI Component) - Version 2

### 1. Vision & Abstract Workspace
The purpose of the `mysim` Web UI is to provide a clean, lightweight, and highly accessible browser interface for interacting with the core financial simulation engine. The UI allows users to load existing configuration scenarios, make transient "what-if" modifications to the model parameters in real time, execute the simulation, and visually analyze the annual results.

#### 1.1 Explicit UI ↔ Engine Boundary Contract
The Web UI acts exclusively as a presentation and orchestration layer. No financial calculations, tax logic, or mutation side effects may exist within Flask route handlers, templates, JavaScript utilities, or export adapters. All financial logic must remain strictly delegated to the core simulation engine. This separation ensures that UI-layer tax calculations or business logic creep is avoided.

---

### 2. Core Technical Constraints
* **Language & Runtime:** Python 3.11+ (sharing the exact same platform and runtime dependencies as the core engine).
* **Framework Layer:** Strictly built using standard **Flask**. Heavy enterprise web frameworks (e.g., Django) or complex client-side JavaScript frameworks are entirely out of scope.
* **Security & Multi-Tenancy:** Out of scope. No user authentication, session persistence across different users, or multi-tenant permission layers are required.
* **Numerical Precision:** All input fields and formatted table displays must preserve fixed-point decimal arithmetic (`Decimal`) via string conversion, avoiding binary floating-point rounding errors during form transmission.
* **Browser Compatibility:** Target browsers are modern evergreen Chromium- and Firefox-based desktop browsers. Legacy Internet Explorer compatibility is explicitly out of scope.
* **Mobile Support:** While primarily designed for desktop, the UI must provide basic mobile compatibility, including responsive tables (horizontal scroll) and larger tap targets for touch-based interaction.
* **Single-user Assumption:** The application is designed for single-user operation. Concurrent edits, process contention, and filesystem races are out of scope for the current architecture.

---

### 3. Architecture & Operational Semantics

#### 3.1 Request Lifecycle Semantics
Each simulation execution operates on a fully isolated in-memory state instance scoped strictly to the active HTTP request lifecycle. This prevents accidental cross-request leakage and ensures thread-safety for future scaling.

#### 3.2 Post/Redirect/Get (PRG) Pattern
Simulation execution routes must follow the Post/Redirect/Get pattern. Upon form submission, the application processes the simulation and redirects to a GET-based results view. This avoids duplicate submissions during browser refresh operations and maintains a clean browser history.

#### 3.3 State Persistence & Workflow Continuity
To ensure workflow continuity without server-side sessions, transient state (including configuration mutations and table view settings like column selection) should be persisted via URL parameters. This approach ensures that the application remains bookmarkable, supports browser "refresh" without data loss, and aligns with the single-user, stateless architecture.

---

### 4. File System & Security Isolation
* **Storage Isolation:** The application is bounded to one single, dedicated local directory on the file system (e.g., `./scenarios/`).
* **Name Sanitization:** The scenario name parameter provided via the URL or interface must be validated against a strict regular expression: `^[a-z0-9_-]+$` (alphanumeric, lower-case, underscores, and hyphens). The maximum length for a scenario name is 64 characters.
* **Resolution Mapping:** The validated parameter maps directly to `<name>.yaml` within the dedicated folder. No paths outside this directory may be resolved.
* **Safe YAML Loading:** YAML parsing must use safe deserialization exclusively (`yaml.safe_load` or equivalent). Arbitrary object deserialization is strictly prohibited.
* **Security Hardening & Limits:**
    * **File Size Limits:** Maximum YAML configuration size is 1MB. Maximum export file size is 10MB.
    * **Rate Limiting:** To prevent abuse, the system should implement basic rate limiting (e.g., maximum 10 simulation executions per minute).
* **Temporary Artifact Lifecycle:** Files generated for exports (CSV/XLSX) should be stored in a dedicated temporary directory (e.g., `/tmp/mysim_exports/`). An automated cleanup policy must be in place to delete files older than 1 hour.

---

### 5. Interface Workflow & The Adjustment Layer

#### 5.1 Stage 1: The Index Page (Scenario Browser)
* **Behavior:** Automatically scans the isolated scenarios directory.
* **Presentation:** Filters out invalid files and displays a clean, direct-access list of available scenarios.

#### 5.2 Stage 2: The Configuration View (The Adjustment Layer)
* **Form Layout:** Parses the target YAML file into an editable HTML form.
    * **Simple Parameters:** Flat scalar variables (e.g., `birth_year: 1974`, `label: "Tagesgeld"`) are mapped to standard, labeled HTML form inputs.
    * **Complex Parameters:** Structured compound blocks (e.g., `capital_sources: {tagesgeld: {...}}`, `events: - year: 2030...`) and arrays of scalars (e.g., `capital_withdrawal_order: ["a", "b"]`) are rendered inside a single HTML `<textarea>` for direct textual editing in YAML format.
* **YAML Parsing & Failure Semantics:** The application must implement a validation pipeline. Invalid YAML structures, schema violations, or plugin resolution failures must trigger a fail-fast behavior, rendering a deterministic, human-readable diagnostics page instead of partially executing the simulation.
* **Transient Principle:** Submitting this form processes the mutated parameters purely in-memory. The master YAML file on disk **must not** be overwritten.
* **UI State Persistence:** The UI state is intentionally ephemeral. However, mutations and dynamic layout changes (e.g., column visibility) should be persisted via URL parameters to support page reloads and bookmarking as specified in Section 3.3.
* **Unsaved Changes Warning:** If the user attempts to navigate away from the Configuration View with unsaved changes in the form, the browser must display a confirmation dialog (via `window.onbeforeunload`).

---

### 6. Table Presentation & Customization Layer
* **UI Scalability:** The implementation prioritizes simplicity and full-page server-side rendering. Client-side virtualization or infinite scrolling is not required; standard full-page renders are acceptable for typical simulation lengths.
* **Dynamic Column Selection:** Users can dynamically select which financial fields to display and alter their sequence. This configuration is transient but must be persisted in URL query parameters (e.g., `?cols=year,age,total_inflows`) for bookmarkability.
* **Audit Accordions:**
    * **Behavior:** Each annual row can be toggled to expand an HTML `<details>` or accordion container exposing the structured calculation derivation trace.
    * **Optimization:** To ensure performance, derivation traces should be lazy-loaded (fetched via AJAX when the accordion opens). All accordions must be collapsed by default.
    * **Depth Limit:** Derivation traces displayed in the UI should be limited to a reasonable depth (e.g., max 20 steps per year).
* **Sorting & Formatting Semantics:** Financial values must be rendered using German locale formatting (e.g., `1.234,56 €`). This includes correct decimal separators, thousands separators, and negative value rendering.
* **HTML Escaping / Output Encoding:** All rendered output, including YAML labels and derivation traces, must be subject to auto-escaping. Raw HTML rendering is prohibited.
* **Print Optimization:** Dedicated print stylesheet using `@media print`.
    * **Layout:** Forced landscape orientation (`@page { size: A4 landscape; }`).
    * **Pagination:** Avoid splitting table rows across page breaks. Include the scenario name, execution timestamp, and page numbers in headers or footers.
    * **Visibility:** Hide non-essential UI elements (navigation, configuration forms, buttons) in the print view.
* **Export Utilities:**
    * **Scope:** Exports must contain the full raw dataset generated by the engine.
    * **File Naming:** `{scenario}_{timestamp}.{ext}`.
    * **CSV Specifications:** Use `;` as the delimiter (German locale). No traces included.
    * **XLSX Specifications:** Built using `openpyxl`. Must include frozen header rows, bold headers, and proper German numeric cell formatting. Inclusion of derivation traces should be a configurable option.

---

### 7. Accessibility
The interface must be highly accessible, adhering to the following:
* **Keyboard Navigation:** All interactive elements must be reachable and operable via keyboard.
* **Semantic HTML:** Use of proper tags (`<nav>`, `<main>`, `<table>`, `<label>`) to ensure screen reader support.
* **Contrast & Readability:** Ensure high contrast for print and screen, with readable font sizes.
* **Progressive Enhancement & JS Dependency:** Core functionality must remain accessible even if JavaScript is disabled.
    * **Feature Matrix:**
        * Scenario Browsing: Works without JS (Server-rendered HTML).
        * Configuration Form: Works without JS (Standard HTML form).
        * Simulation Execution: Works without JS (PRG pattern).
        * Column Selection: Requires JS (Hidden if disabled).
        * Audit Accordions: Requires JS (Fallback: Show all traces expanded if disabled, or provide a server-rendered alternative).
        * Dynamic Sorting: Requires JS (Default sort by year).
    * **Fallback:** A `<noscript>` warning must be displayed: "For full functionality (e.g., column selection, accordions), please enable JavaScript."

---

### 8. Future Feature Scope (Deferred Implementation)
* **The "Save As" Facility:** A secure UI option to save mutated configurations back to the filesystem as new files.
* **Schema-aware YAML Enhancement:** Intelligent editor features for the YAML textarea.

---

### 9. Error Handling
The application must provide clear, actionable feedback when errors occur.
* **Error Mapping:**
    * **Scenario Not Found:** HTTP 404. "Scenario '{name}' does not exist." Provide a link back to the scenario list.
    * **Invalid YAML:** HTTP 400. "YAML syntax error." Display the specific line and context of the error.
    * **Schema Violation:** HTTP 400. "Configuration error." Highlight missing or invalid fields according to the engine's schema.
    * **Simulation Failure:** HTTP 500. "Simulation failed." Provide a descriptive error message (e.g., invariant violation) and a state snapshot if applicable.
    * **Export Error:** HTTP 500. "Failed to generate export."
* **Operational Guidelines:**
    * Log all errors to a server-side log file for diagnostics.
    * **Security:** Never expose raw Python stack traces to the end-user.

---

### 10. Performance Requirements
The UI must remain responsive and performant under typical usage.
* **Scenario Listing:** Load and display the scenario list in < 500ms (for up to 100 scenarios).
* **Table Rendering:** Render a 50-year simulation results table in < 2 seconds.
* **Exports:** Generate and initiate download of CSV/XLSX exports for a 100-year simulation in < 3 seconds.

---

### 11. Testing Requirements
To ensure stability and accessibility, the following testing layers are mandatory:
* **Unit Tests:** Coverage for Flask route logic, form parsing, and validation helpers (using `pytest`).
* **Integration Tests:** End-to-end verification of the PRG flow, from configuration adjustment to result display.
* **Accessibility Testing:** Automated (e.g., `axe-core`) and manual audits to ensure keyboard operability and screen reader compatibility.
* **Cross-browser Testing:** Verification of layout and functionality in modern Chromium and Firefox browsers (using `Playwright`).
* **Performance Benchmarking:** Automated checks to ensure performance thresholds (Section 10) are maintained.
