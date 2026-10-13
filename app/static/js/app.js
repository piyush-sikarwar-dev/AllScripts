// Small progressive enhancements. Loaded from 'self' only; no inline handlers (CSP).
(function () {
  "use strict";

  // Print button.
  document.addEventListener("click", function (evt) {
    if (evt.target.closest("[data-action='print']")) {
      window.print();
    }
  });

  // Records release: the PDF is built on the server (large records take a while) and arrives as a
  // download, so the page never changes. Show progress, block double submits, and tell the user
  // when the download has started (the server echoes a random token in a short-lived cookie).
  var EXPORT_COOKIE = "export_download";

  function exportCookie() {
    var match = document.cookie.match(new RegExp("(?:^|; )" + EXPORT_COOKIE + "=([^;]*)"));
    return match ? match[1] : "";
  }

  document.addEventListener("submit", function (evt) {
    var form = evt.target;
    if (!form.matches || !form.matches("[data-export-form]")) {
      return;
    }
    var button = form.querySelector("[data-export-submit]");
    var status = form.querySelector("[data-export-status]");
    var token = "";
    for (var i = 0; i < 4; i++) {
      token += Math.random().toString(36).slice(2, 8);
    }
    var field = form.querySelector("input[name='download_token']");
    if (!field) {
      field = document.createElement("input");
      field.type = "hidden";
      field.name = "download_token";
      form.appendChild(field);
    }
    field.value = token.replace(/[^a-z0-9]/gi, "").slice(0, 32);
    if (status) {
      status.textContent = "Creating PDF… Large records can take a few minutes. " +
        "The download starts by itself — keep this page open.";
    }
    window.setTimeout(function () {
      if (button) {
        button.disabled = true;
        button.textContent = "Creating PDF…";
      }
    }, 0);
    var started = Date.now();
    var timer = window.setInterval(function () {
      var done = exportCookie() === field.value;
      if (!done && Date.now() - started < 15 * 60 * 1000) {
        return;
      }
      window.clearInterval(timer);
      if (button) {
        button.disabled = false;
        button.textContent = "Create PDF";
      }
      if (status) {
        status.textContent = done
          ? "PDF ready — check your downloads."
          : "Still no download. Check the release log, or try again with fewer sections.";
      }
    }, 1000);
  });

  // Visit / note lists: mark the clicked row as selected once its detail has loaded.
  var ROW_CLASSES = ["visit-row", "note-row", "entry-row"];
  document.addEventListener("htmx:afterRequest", function (evt) {
    var row = evt.detail.elt;
    var kind = row.classList && ROW_CLASSES.filter(function (c) {
      return row.classList.contains(c);
    })[0];
    if (!evt.detail.successful || !kind) {
      return;
    }
    document.querySelectorAll("." + kind + "--selected").forEach(function (el) {
      el.classList.remove(kind + "--selected");
      el.removeAttribute("aria-current");
    });
    row.classList.add(kind + "--selected");
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

  // "Add to export" changes what the Visits tab shows: forget its remembered copy.
  document.addEventListener("htmx:afterRequest", function (evt) {
    var cfg = evt.detail.requestConfig;
    if (cfg && cfg.verb === "post" && /\/export-selection\//.test(cfg.path)) {
      tabCache.forEach(function (_entry, path) {
        if (/\/tab\/visits$/.test(path)) {
          tabCache.delete(path);
        }
      });
    }
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
