// SPDX-FileCopyrightText: 2026 ff-fab
// SPDX-License-Identifier: MIT

/**
 * Synchronise the light / dark palette choice across all cosalette-apps
 * documentation sites.
 *
 * Material for MkDocs (and Zensical) stores the palette preference in
 * localStorage under a **path-scoped** key (`<pathname>.__palette`), so
 * each sub-site has its own independent preference.  This script writes
 * the chosen colour *scheme* (e.g. "slate" or "default") to a single
 * shared key (`cosalette-palette-scheme`) and applies it on every page
 * load — before the first paint — so all sites stay in sync.
 *
 * Only the scheme is synchronised; primary/accent colours remain
 * per-site (the root site uses amber/orange, app sites use teal/cyan).
 */
(function () {
  "use strict";

  var STORAGE_KEY = "cosalette-palette-scheme";

  // ── On load: apply the shared scheme before the theme renders ──────
  // This block runs synchronously (the script tag has no `defer`), so it
  // executes before DOMContentLoaded and prevents a flash of the wrong
  // scheme.
  try {
    var saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      document.body.setAttribute("data-md-color-scheme", saved);
      // Sync the theme's own path-scoped palette so the toggle icon matches.
      var scopedKey = new URL(document.baseURI).pathname + ".__palette";
      var palette = JSON.parse(localStorage.getItem(scopedKey) || "null");
      if (palette && palette.color && palette.color.scheme !== saved) {
        palette.color.scheme = saved;
        palette.index = saved === "slate" ? 0 : 1;
        localStorage.setItem(scopedKey, JSON.stringify(palette));
      }
    }
  } catch (e) {
    /* localStorage unavailable — degrade gracefully */
  }

  // ── After DOM ready: watch the palette toggle and persist changes ───
  function watch() {
    // The palette toggle is a <form data-md-component="palette"> with
    // hidden <input> elements; the theme toggles them on click/Enter.
    var form = document.querySelector("[data-md-component=palette]");
    if (!form) return;

    // Use MutationObserver on <body> to detect scheme changes reliably,
    // since the theme sets data-md-color-scheme on the body element.
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === "data-md-color-scheme") {
          var scheme = document.body.getAttribute("data-md-color-scheme");
          if (scheme) {
            try {
              localStorage.setItem(STORAGE_KEY, scheme);
            } catch (e) {
              /* best-effort */
            }
          }
          break;
        }
      }
    });

    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ["data-md-color-scheme"],
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", watch);
  } else {
    watch();
  }
})();
