// Visit print page: open the browser's print dialog once the page has loaded (CSP: no inline JS).
(function () {
  "use strict";
  window.addEventListener("load", function () {
    window.print();
  });
})();
