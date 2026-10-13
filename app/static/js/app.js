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
  function focusMarked() {
    var focusEl = document.querySelector("[data-focus-on-load]");
    if (focusEl) {
      focusEl.removeAttribute("data-focus-on-load");
      focusEl.focus({ preventScroll: true });
    }
  }
  document.addEventListener("htmx:afterSettle", focusMarked);

  // ---------------------------------------------------------------------------------------------
  // Chart tabs already opened on this page are shown again from page memory (perf #7).
  // - Only plain tab clicks (<a role="tab">); filters, pagers and detail panels always ask the
  //   server. Memory only: gone when the page is left; never stored on disk.
  // - An entry is reused for at most 10 minutes (shorter than the 15-minute idle sign-out).
  // - Each re-show is still audited: a small CSRF-protected POST records the view; if the
  //   session has ended, the browser is sent to the sign-in page.
  var TAB_PATH = /^\/patients\/[^/?#]+\/tab\/[a-z]+$/;
  var MAX_AGE_MS = 10 * 60 * 1000;
  var MAX_ENTRIES = 30;
  var tabCache = new Map();
  // The clicked tab is replaced during the swap, so tab requests are recognised by their XHR.
  var pendingTabRequests = new WeakMap();

  function tabRequest(detail) {
    var cfg = detail.requestConfig;
    var elt = detail.elt;
    if (!cfg || cfg.verb !== "get" || !elt || !elt.matches || !elt.matches("a[role='tab']")) {
      return null;
    }
    return TAB_PATH.test(cfg.path) ? cfg.path : null;
  }

  function csrfToken() {
    try {
      return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRF-Token"] || "";
    } catch (e) {
      return "";
    }
  }

  function recordView(path) {
    fetch(path + "/seen", {
      method: "POST",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken(), "HX-Request": "true" },
      keepalive: true,
    }).then(function (resp) {
      if (resp.status !== 204) {
        window.location.assign("/login");
      }
    }).catch(function () {
      /* network hiccup: the next server request will handle the session */
    });
  }

  document.addEventListener("htmx:beforeRequest", function (evt) {
    var path = tabRequest(evt.detail);
    if (!path) {
      return;
    }
    var hit = tabCache.get(path);
    if (!hit || Date.now() - hit.at > MAX_AGE_MS) {
      tabCache.delete(path);
      if (evt.detail.xhr) {
        pendingTabRequests.set(evt.detail.xhr, path);
      }
      return;
    }
    evt.preventDefault();
    window.htmx.swap(evt.detail.target, hit.html, { swapStyle: "outerHTML" });
    if (hit.pushUrl) {
      window.history.pushState({ htmx: true }, "", hit.pushUrl);
    }
    focusMarked();
    recordView(path);
  });

  document.addEventListener("htmx:afterRequest", function (evt) {
    var xhr = evt.detail.xhr;
    var path = xhr ? pendingTabRequests.get(xhr) : null;
    if (!path || !evt.detail.successful || xhr.status !== 200) {
      return;
    }
    pendingTabRequests.delete(xhr);
    tabCache.delete(path);
    tabCache.set(path, {
      html: xhr.responseText,
      pushUrl: xhr.getResponseHeader("HX-Push-Url"),
      at: Date.now(),
    });
    if (tabCache.size > MAX_ENTRIES) {
      tabCache.delete(tabCache.keys().next().value);
    }
  });
})();
