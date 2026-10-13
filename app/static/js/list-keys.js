// Lists of rows (Notes tab): Up / Down arrows move focus between rows; Enter opens the row.
// Loaded from 'self' only (CSP); no inline handlers.
(function () {
  "use strict";

  document.addEventListener("keydown", function (evt) {
    if (evt.key !== "ArrowDown" && evt.key !== "ArrowUp") {
      return;
    }
    var row = evt.target.closest && evt.target.closest("[data-list-row]");
    if (!row) {
      return;
    }
    var rows = Array.prototype.slice.call(
      row.closest("[data-list]").querySelectorAll("[data-list-row]")
    );
    var next = rows[rows.indexOf(row) + (evt.key === "ArrowDown" ? 1 : -1)];
    if (next) {
      evt.preventDefault();
      next.focus();
    }
  });
})();
