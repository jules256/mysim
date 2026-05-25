
# Software Requirements Specification (SRS)
## Project: mysim (Web UI Component)

### 1. Vision & Abstract Workspace
The purpose of the `mysim` Web UI is to provide a clean, lightweight, and highly accessible browser interface for interacting with the core financial simulation engine. The UI allows users to load existing configuration scenarios, make transient "what-if" modifications to the model parameters in real time, execute the simulation, and visually analyze the annual results. The presentational layer must remain completely decoupled from the core calculation logic.

---

### 2. Core Technical Constraints
* **Language & Runtime:** Python 3.11+ (sharing the exact same platform and runtime dependencies as the core engine).
* **Framework Layer:** Strictly built using standard **Flask**. Heavy enterprise web frameworks (e.g., Django) or complex client-side JavaScript frameworks are entirely out of scope.
* **Security & Multi-Tenancy:** Out of scope. No user authentication, session persistence across different users, or multi-tenant permission layers are required for this iteration.
* **Numerical Precision:** All input fields and formatted table displays must preserve fixed-point decimal arithmetic (`Decimal`) via string conversion, avoiding binary floating-point rounding errors during form transmission.

---

### 3. File System & Security Isolation
To prevent directory traversal exploits and maintain a strictly isolated configuration environment, the following rules apply:
* **Storage Isolation:** The application is bounded to one single, dedicated local directory on the file system (e.g., `./scenarios/`).
* **Name Sanitization:** The scenario name parameter provided via the URL or interface must be validated against a strict regular expression: `^[a-z0-9]+$` (alphanumeric, lower-case only).
* **Resolution Mapping:** The validated parameter maps directly to `<name>.yaml` within the dedicated folder. No paths outside this directory may be resolved, loaded, or evaluated. Attempted violations must fail-fast and redirect to the index view.

---

### 4. Interface Workflow & The Adjustment Layer
The application operates on a lean, traditional three-stage interaction loop:

#### Stage 1: The Index Page (Scenario Browser)
* **Behavior:** Automatically scans the isolated scenarios directory.
* **Presentation:** Filters out invalid files and displays a clean, direct-access list of available scenarios by their alphanumeric identifier. Clicking an identifier routes the user to Stage 2.

#### Stage 2: The Configuration View (The Adjustment Layer)
* **Form Layout:** Parses the target YAML file into an editable HTML form.
    * **Simple Parameters:** Flat variables (e.g., `birth_year`, `baseline_inflation_rate`) are mapped to standard, labeled HTML form inputs.
    * **Complex Parameters:** Structured compound blocks (e.g., `capital_sources` and scheduled `events`) are rendered inside a single, clean HTML `<textarea>` prepopulated with formatted YAML markup for direct textual editing. If a stable, lightweight YAML editing script component is easily available, it may be integrated to enhance readability.
* **Transient Principle:** Submitting this form processes the mutated parameters purely in-memory. The master YAML file on disk **must not** be overwritten.

#### Stage 3: The Result View (The Output Matrix)
* **Execution:** Feeds the adjusted configuration directly into the core engine execution loop.
* **Presentation:** Receives the transient in-memory output matrix and outputs it as a rich, single-page data table where each simulated calendar year occupies exactly one horizontal row.

---

### 5. Table Presentation & Customization Layer
The simulation table view must balance user comfort with architectural simplicity.

* **Dynamic Column Selection & Ordering:** The interface must provide a sidebar or header utility block featuring checkboxes and up/down positioning toggles. Users can dynamically select which financial fields to display and alter their sequence on the fly during runtime. This configuration can optionally seed from metadata inside the loaded scenario block.
* **Audit Accordions:** To support the engine's calculation auditability, each annual row in the table can be toggled to expand an HTML `<details>` or accordion container. This container exposes the structured calculation derivation trace (explaining precisely how complex metrics like German income taxes or health insurance fees were computed for that specific year).
* **Print Optimization:** The interface must include a dedicated print stylesheet using native CSS print media queries (`@media print`). When triggered, the print stylesheet strips away the web navigation bars, configuration controls, and background colors, delivering a clean, printer-friendly, professional tabular document.
* **Export Utilities:** The view must feature prominent action hooks allowing the active in-memory dataset to be compiled and downloaded instantly as raw **CSV** or styled **XLSX** files.

---

### 6. Future Feature Scope (Deferred Implementation)
The following feature is planned for future product iterations and **must not** be included in the initial implementation phase:
* **The "Save As" Facility:** A secure UI option that will allow a user to save their
