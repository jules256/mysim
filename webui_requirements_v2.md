
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
* **Single-user Assumption:** The application is designed for single-user operation. Concurrent edits, process contention, and filesystem races are out of scope for the current architecture.

---

### 3. Architecture & Operational Semantics

#### 3.1 Request Lifecycle Semantics
Each simulation execution operates on a fully isolated in-memory state instance scoped strictly to the active HTTP request lifecycle. This prevents accidental cross-request leakage and ensures thread-safety for future scaling.

#### 3.2 Post/Redirect/Get (PRG) Pattern
Simulation execution routes must follow the Post/Redirect/Get pattern. Upon form submission, the application processes the simulation and redirects to a GET-based results view. This avoids duplicate submissions during browser refresh operations and maintains a clean browser history.

---

### 4. File System & Security Isolation
* **Storage Isolation:** The application is bounded to one single, dedicated local directory on the file system (e.g., `./scenarios/`).
* **Name Sanitization:** The scenario name parameter provided via the URL or interface must be validated against a strict regular expression: `^[a-z0-9]+$` (alphanumeric, lower-case only).
* **Resolution Mapping:** The validated parameter maps directly to `<name>.yaml` within the dedicated folder. No paths outside this directory may be resolved.
* **Safe YAML Loading:** YAML parsing must use safe deserialization exclusively (`yaml.safe_load` or equivalent). Arbitrary object deserialization is strictly prohibited.
* **Temporary Artifact Lifecycle:** Files generated for exports (CSV/XLSX) should ideally be streamed directly or stored in a dedicated temporary directory with an automated cleanup policy.

---

### 5. Interface Workflow & The Adjustment Layer

#### 5.1 Stage 1: The Index Page (Scenario Browser)
* **Behavior:** Automatically scans the isolated scenarios directory.
* **Presentation:** Filters out invalid files and displays a clean, direct-access list of available scenarios.

#### 5.2 Stage 2: The Configuration View (The Adjustment Layer)
* **Form Layout:** Parses the target YAML file into an editable HTML form.
    * **Simple Parameters:** Flat variables are mapped to standard, labeled HTML form inputs.
    * **Complex Parameters:** Structured compound blocks are rendered inside a single HTML `<textarea>` for direct textual editing.
* **YAML Parsing & Failure Semantics:** The application must implement a validation pipeline. Invalid YAML structures, schema violations, or plugin resolution failures must trigger a fail-fast behavior, rendering a deterministic, human-readable diagnostics page instead of partially executing the simulation.
* **Transient Principle:** Submitting this form processes the mutated parameters purely in-memory. The master YAML file on disk **must not** be overwritten.
* **UI State Persistence:** The UI state is intentionally ephemeral. Mutations and dynamic layout changes (e.g., column visibility) do not survive page reloads.

---

### 6. Table Presentation & Customization Layer
* **UI Scalability:** The implementation prioritizes simplicity and full-page server-side rendering. Client-side virtualization or infinite scrolling is not required; standard full-page renders are acceptable for typical simulation lengths.
* **Dynamic Column Selection:** Users can dynamically select which financial fields to display and alter their sequence. This configuration is transient.
* **Audit Accordions:** Each annual row can be toggled to expand an HTML `<details>` or accordion container exposing the structured calculation derivation trace.
* **Sorting & Formatting Semantics:** Financial values must be rendered using German locale formatting (e.g., `1.234,56 €`). This includes correct decimal separators, thousands separators, and negative value rendering.
* **HTML Escaping / Output Encoding:** All rendered output, including YAML labels and derivation traces, must be subject to auto-escaping. Raw HTML rendering is prohibited.
* **Print Optimization:** Dedicated print stylesheet using `@media print` to deliver a clean, professional tabular document.
* **Export Utilities:**
    * **Scope:** Exports must contain the full raw dataset generated by the engine.
    * **XLSX Requirements:** Minimal professional styling (frozen header rows, bold headers, proper numeric cell formatting). No complex macros or formulas are required.

---

### 7. Accessibility
The interface must be highly accessible, adhering to the following:
* **Keyboard Navigation:** All interactive elements must be reachable and operable via keyboard.
* **Semantic HTML:** Use of proper tags (`<nav>`, `<main>`, `<table>`, `<label>`) to ensure screen reader support.
* **Contrast & Readability:** Ensure high contrast for print and screen, with readable font sizes.
* **JS Dependency:** The core functionality should remain functional even with minimal JavaScript.

---

### 8. Future Feature Scope (Deferred Implementation)
* **The "Save As" Facility:** A secure UI option to save mutated configurations back to the filesystem as new files.
* **Schema-aware YAML Enhancement:** Intelligent editor features for the YAML textarea.
