// Small progressive enhancements. Loaded from 'self' only; no inline handlers (CSP).
(function () {
  "use strict";

  // Print button.
  document.addEventListener("click", function (evt) {
    if (evt.target.closest("[data-action='print']")) {
      window.print();
    }
  });

  // Visit list: mark the clicked row as selected once its detail has loaded.
  document.addEventListener("htmx:afterRequest", function (evt) {
    var row = evt.detail.elt;
    if (!evt.detail.successful || !row.classList || !row.classList.contains("visit-row")) {
      return;
    }
    document.querySelectorAll(".visit-row--selected").forEach(function (el) {
      el.classList.remove("visit-row--selected");
      el.removeAttribute("aria-current");
    });
    row.classList.add("visit-row--selected");
    row.setAttribute("aria-current", "true");
  });

  // After a tab or visit swap, move focus to the new content's heading for screen readers.
  // Fragments mark that element with data-focus-on-load (only in HTMX responses).
  document.addEventListener("htmx:afterSettle", function () {
    var focusEl = document.querySelector("[data-focus-on-load]");
    if (focusEl) {
      focusEl.removeAttribute("data-focus-on-load");
      focusEl.focus({ preventScroll: true });
    }
  });
})();
