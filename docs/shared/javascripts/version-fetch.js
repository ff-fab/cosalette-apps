// SPDX-FileCopyrightText: 2026 ff-fab
// SPDX-License-Identifier: MIT

/**
 * Fetch the latest GitHub release for this app and display it in the
 * Material for MkDocs version element.  Results are cached in
 * sessionStorage so the GitHub API is hit at most once per browser session.
 */
(function () {
  "use strict";

  var REPO = "ff-fab/cosalette-apps";
  var API = "https://api.github.com/repos/" + REPO + "/releases";
  var CACHE_PREFIX = "cosalette-version:";

  /** Derive the app name from the site_name meta tag. */
  function getAppName() {
    var meta = document.querySelector("meta[property='og:site_name']");
    return meta ? meta.content.trim() : null;
  }

  /** Set the version text and make the element visible. */
  function applyVersion(version) {
    var el = document.querySelector(".md-source__fact--version");
    if (!el) return;
    el.textContent = version;
    el.style.display = "";
  }

  function run() {
    var app = getAppName();
    if (!app) return;

    var cacheKey = CACHE_PREFIX + app;
    var cached = sessionStorage.getItem(cacheKey);
    if (cached) {
      applyVersion(cached);
      return;
    }

    var prefix = app + "-v";

    fetch(API + "?per_page=100")
      .then(function (res) {
        return res.ok ? res.json() : Promise.reject(res.status);
      })
      .then(function (releases) {
        for (var i = 0; i < releases.length; i++) {
          var tag = releases[i].tag_name || "";
          if (tag.indexOf(prefix) === 0) {
            var version = tag.slice(app.length + 1); // strip "<app>-"
            sessionStorage.setItem(cacheKey, version);
            applyVersion(version);
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
