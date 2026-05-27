/**
 * mysim Web UI - Client-side JavaScript
 * Progressive enhancement: core functionality works without JS.
 */
(function () {
    "use strict";

    // Mark JS as enabled
    document.documentElement.classList.add("js-enabled");

    // --- Unsaved changes warning ---
    const configForm = document.getElementById("config-form");
    if (configForm) {
        let formChanged = false;

        configForm.addEventListener("input", function () {
            formChanged = true;
        });

        configForm.addEventListener("submit", function () {
            formChanged = false;
        });

        window.addEventListener("beforeunload", function (e) {
            if (formChanged) {
                e.preventDefault();
                e.returnValue = "";
            }
        });
    }

    // --- Column selector form: build cols param ---
    const colsForm = document.getElementById("cols-form");
    if (colsForm) {
        colsForm.addEventListener("submit", function (e) {
            e.preventDefault();
            const checked = colsForm.querySelectorAll('input[name="col"]:checked');
            const cols = Array.from(checked).map(function (cb) { return cb.value; });

            const url = new URL(colsForm.action, window.location.origin);
            const cfg = colsForm.querySelector('input[name="cfg"]').value;
            if (cfg) {
                url.searchParams.set("cfg", cfg);
            }
            if (cols.length > 0) {
                url.searchParams.set("cols", cols.join(","));
            }
            window.location.href = url.toString();
        });
    }

    // --- Lazy-load trace accordions ---
    document.addEventListener("toggle", function (e) {
        var details = e.target;
        if (!details.classList || !details.classList.contains("trace-accordion")) {
            return;
        }
        if (!details.open) {
            return;
        }

        var content = details.querySelector(".trace-content");
        if (!content || content.dataset.loaded === "true") {
            return;
        }

        var year = details.dataset.year;
        var scenario = details.dataset.scenario;
        var cfg = details.dataset.cfg;
        var url = "/scenario/" + encodeURIComponent(scenario) + "/trace/" + encodeURIComponent(year) + "?cfg=" + encodeURIComponent(cfg);

        fetch(url)
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }
                return response.text();
            })
            .then(function (html) {
                content.innerHTML = html;
                content.dataset.loaded = "true";
            })
            .catch(function (err) {
                content.innerHTML = '<p class="trace-empty">Fehler beim Laden: ' + err.message + '</p>';
            });
    }, true);

})();
