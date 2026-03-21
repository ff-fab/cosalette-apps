// SPDX-FileCopyrightText: 2026 ff-fab
// SPDX-License-Identifier: MIT

/**
 * Fetch the latest GitHub release for this app and display it in the
 * Material for MkDocs version element.  Results are cached in
 * sessionStorage so the GitHub API is hit at most once per browser session.
 *
 * A MutationObserver guards against the theme's own JS overwriting our
 * value with the repo-wide latest release (which belongs to a different app
 * in this monorepo).
 */
(function () {
  "use strict";

  var REPO = "ff-fab/cosalette-apps";
  var API = "https://api.github.com/repos/" + REPO + "/releases";
  var CACHE_PREFIX = "cosalette-version:";

  /** Derive the app name from the page title ("Page - site_name"). */
  function getAppName() {
    var title = document.title || "";
    var sep = title.lastIndexOf(" - ");
    return sep > 0 ? title.slice(sep + 3).trim() : null;
  }

  function storageGet(key) {
    try {
      return sessionStorage.getItem(key);
    } catch (e) {
      return null;
    }
  }

  function storageSet(key, val) {
    try {
      sessionStorage.setItem(key, val);
    } catch (e) {
      /* best-effort — storage may be disabled in private browsing */
    }
  }

  /**
   * Set the version text, make the element visible, and install a
   * MutationObserver that re-applies our value if the theme's JS
   * overwrites it (race condition with Material's own release fetch).
   */
  function applyAndGuard(el, version) {
    el.textContent = version;
    el.style.display = "inline";

    var observer = new MutationObserver(function () {
      observer.disconnect();
      el.textContent = version;
      el.style.display = "inline";
    });
    observer.observe(el, {
      childList: true,
      characterData: true,
      subtree: true,
    });
    // Safety cleanup — Material should be done well within 30 s.
    setTimeout(function () {
      observer.disconnect();
    }, 30000);
  }

  function run() {
    var app = getAppName();
    if (!app) return;

    var el = document.querySelector(".md-source__fact--version");
    if (!el) return;

    // Hide immediately to prevent flash of wrong (repo-wide) version.
    el.style.display = "none";

    var cacheKey = CACHE_PREFIX + app;
    var cached = storageGet(cacheKey);
    if (cached) {
      applyAndGuard(el, cached);
      return;
    }

    var prefix = app + "-v";

    // Note: per_page=100 covers ~33 releases per app (3 apps). If the repo
    // exceeds 100 total releases, consider switching to the tags API.
    fetch(API + "?per_page=100")
      .then(function (res) {
        return res.ok ? res.json() : Promise.reject(res.status);
      })
      .then(function (releases) {
        for (var i = 0; i < releases.length; i++) {
          var tag = releases[i].tag_name || "";
          if (tag.indexOf(prefix) === 0) {
            var version = tag.slice(app.length + 1); // strip "<app>-"
            applyAndGuard(el, version);
            storageSet(cacheKey, version);
            return;
          }
        }
      })
      .catch(function () {
        // Silently ignore — the version element stays hidden.
      });
  }

  // Run after the DOM is ready.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", run);
  } else {
    run();
  }
})();
