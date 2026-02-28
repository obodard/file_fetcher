// app.js — file_fetcher web UI helpers

// ── AI toggle (global, used by filter_bar.html onclick) ────────────────────────
function toggleAiMode(btn) {
  const pressed = btn.getAttribute("aria-pressed") === "true";
  const next = !pressed;
  btn.setAttribute("aria-pressed", String(next));
  btn.setAttribute("aria-label", "AI Search mode " + (next ? "active" : "inactive"));
  btn.classList.toggle("btn-primary", next);
  btn.classList.toggle("btn-ghost", !next);
  document.getElementById("ai-hidden").value = next ? "1" : "0";
  // Trigger the filter form to reload the grid
  htmx.trigger(document.getElementById("filter-bar"), "change");
}

// ── Load-more manual fallback (no IntersectionObserver) ──────────────────────
function loadMoreManual(btn) {
  const offset = parseInt(btn.dataset.offset || "0", 10);
  btn.dataset.offset = offset + 40;
  htmx.ajax("GET", btn.getAttribute("hx-get") + "&offset=" + offset, {
    target: "#grid-container",
    swap: "beforeend",
  });
}

// ── Toast auto-dismiss via MutationObserver ────────────────────────────────────
function scheduleToastDismiss(node) {
  if (!node || node.nodeType !== Node.ELEMENT_NODE) return;
  if (node.getAttribute("role") !== "alert") return;
  const delay = node.dataset.toastError ? 5000 : 3000;
  setTimeout(function () {
    node.style.transition = "opacity 0.4s";
    node.style.opacity = "0";
    setTimeout(function () { node.remove(); }, 400);
  }, delay);
}

(function () {
  "use strict";

  // ── Theme toggle ────────────────────────────────────────────────────────────
  const THEME_KEY = "theme";
  const DEFAULT_THEME = "dark";
  const ALT_THEME = "light";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const btn = document.getElementById("theme-toggle");
    if (btn) btn.textContent = theme === "dark" ? "🌙" : "☀️";
  }

  // Apply saved theme immediately on load
  const savedTheme = localStorage.getItem(THEME_KEY) || DEFAULT_THEME;
  applyTheme(savedTheme);

  document.addEventListener("DOMContentLoaded", function () {
    // Re-apply (DOM is now ready for button update)
    applyTheme(localStorage.getItem(THEME_KEY) || DEFAULT_THEME);

    const themeBtn = document.getElementById("theme-toggle");
    if (themeBtn) {
      themeBtn.addEventListener("click", function () {
        const current = document.documentElement.getAttribute("data-theme") || DEFAULT_THEME;
        const next = current === "dark" ? ALT_THEME : DEFAULT_THEME;
        localStorage.setItem(THEME_KEY, next);
        applyTheme(next);
      });
    }

    // ── Toast auto-dismiss (server-rendered toasts from page load) ─────────────
    document.querySelectorAll("[data-toast], [data-toast-error]").forEach(function (el) {
      scheduleToastDismiss(el);
    });

    // ── MutationObserver: auto-dismiss HTMX-injected toasts ───────────────────
    const toastContainer = document.getElementById("toast-container");
    if (toastContainer) {
      new MutationObserver(function (mutations) {
        mutations.forEach(function (m) {
          m.addedNodes.forEach(function (node) {
            // Direct alert added (e.g. make_toast OOB inner div)
            if (node.nodeType === Node.ELEMENT_NODE) {
              if (node.getAttribute("role") === "alert") {
                scheduleToastDismiss(node);
              } else {
                // Wrapper div containing the alert (hx-swap-oob container)
                node.querySelectorAll && node.querySelectorAll("[role=alert]").forEach(scheduleToastDismiss);
              }
            }
          });
        });
      }).observe(toastContainer, { childList: true, subtree: true });
    }

    // ── HTMX responseError fallback — generic error toast ─────────────────────
    document.body.addEventListener("htmx:responseError", function (e) {
      if (!toastContainer) return;
      const wrapper = document.createElement("div");
      wrapper.innerHTML =
        '<div role="alert" class="alert alert-error shadow-lg flex items-center gap-2 pr-2" data-toast-error="true">' +
        '<span class="flex-1 text-sm">Request failed. Please try again.</span>' +
        '<button aria-label="Dismiss" class="btn btn-ghost btn-xs" ' +
        "onclick=\"this.closest('[role=alert]').remove()\">✕</button>" +
        "</div>";
      const alert = wrapper.firstChild;
      toastContainer.appendChild(alert);
      scheduleToastDismiss(alert);
    });

    // ── '/' shortcut → focus search ────────────────────────────────────────────
    document.addEventListener("keydown", function (e) {
      const tag = (document.activeElement || {}).tagName || "";
      if (e.key === "/" && tag !== "INPUT" && tag !== "TEXTAREA" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        const searchInput = document.getElementById("search-input");
        if (searchInput) searchInput.focus();
      }
    });

    // ── Touch / old-browser fallback for infinite scroll ─────────────────────
    if (!("IntersectionObserver" in window)) {
      const loadMoreBtn = document.getElementById("load-more-btn");
      if (loadMoreBtn) {
        loadMoreBtn.classList.remove("hidden");
      }
    }
  });
})();
