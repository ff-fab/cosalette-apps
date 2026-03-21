// SPDX-FileCopyrightText: 2026 ff-fab
// SPDX-License-Identifier: MIT

/**
 * Prepend a "cosalette-apps ›" breadcrumb link to the header title.
 *
 * The link points to the monorepo documentation root and is styled to
 * blend in with the site title — it only reveals itself as a link on
 * hover (see extra.css for the matching styles).
 */
(function () {
  "use strict";

  var MONOREPO_URL = "https://ff-fab.github.io/cosalette-apps/";
  var PREFIX_TEXT = "cosalette-apps";
  var CHEVRON = "\u00a0\u203a\u00a0"; // nbsp › nbsp

  function inject() {
    // Material for MkDocs / Zensical puts the site name inside
    // .md-header__topic > .md-ellipsis
    var topic = document.querySelector(
      ".md-header__topic .md-ellipsis"
    );
    if (!topic) return;

    var appName = topic.textContent.trim();

    // Guard: don't inject on the monorepo root site itself
    if (appName === PREFIX_TEXT) return;

    // Guard: don't inject twice
    if (topic.querySelector(".header-breadcrumb")) return;

    // Build: <a class="header-breadcrumb">cosalette-apps</a> › appName
    var link = document.createElement("a");
    link.href = MONOREPO_URL;
    link.className = "header-breadcrumb";
    link.textContent = PREFIX_TEXT;

    var chevron = document.createElement("span");
    chevron.className = "header-breadcrumb-sep";
    chevron.textContent = CHEVRON;

    // Replace the text node with our breadcrumb + original name
    topic.textContent = "";
    topic.appendChild(link);
    topic.appendChild(chevron);
    topic.appendChild(document.createTextNode(appName));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", inject);
  } else {
    inject();
  }
})();
