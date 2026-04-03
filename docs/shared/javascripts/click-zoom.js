// SPDX-FileCopyrightText: 2026 ff-fab
// SPDX-License-Identifier: MIT

/* click-zoom — Click-to-fullscreen zoom for diagrams, SVGs, and images ---- */
/*                                                                             */
/* Strategies:                                                                 */
/*   1. RE-RENDER — Mermaid diagrams behind closed Shadow DOM                  */
/*   2. FETCH     — <img> elements (SVG fetched inline, raster as <img>)       */
/*   3. CLONE     — Inline <svg> elements via cloneNode(true)                  */
/*                                                                             */
/* Rewritten from the proven cosalette mermaid-zoom.js, extended for images.   */
/* Mermaid zoom uses an opt-out pattern: CSS targets .mermaid directly,        */
/* JS adds .click-zoom-excluded only when zoom would not enlarge the diagram.  */
/* Image/SVG zoom uses an opt-in pattern: JS sets [data-click-zoom] on         */
/* content elements that would benefit from zooming.                           */

;(function () {
  "use strict";

  var overlay = null;
  var prevOverflow = "";
  var lastFocusedElement = null;
  var sourcesByPath = {};
  var renderCounter = 0;
  var MERMAID_KW =
    /^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|gitgraph|mindmap|timeline|quadrantChart|sankey|xychart)\b/i;

  /* ── Mermaid source capture ────────────────────────────────────────── */

  /**
   * Grab the raw Mermaid code before the theme replaces it with Shadow DOM.
   *
   * Priority order:
   *   1. Preserved <script type="text/plain" class="click-zoom-mermaid-source">
   *      elements injected at build time (most reliable).
   *   2. <pre class="mermaid"><code>…</code></pre> elements still in the DOM.
   *   3. Keyword-sniffing: scan all <pre><code> for Mermaid keywords.
   */
  function captureSources() {
    var key = window.location.pathname;
    if (sourcesByPath[key]) return;

    var sources = [];

    // Strategy 1: preserved build-time sources
    var preserved = document.querySelectorAll(
      "script.click-zoom-mermaid-source[type='text/plain']"
    );
    if (preserved.length > 0) {
      preserved.forEach(function (el) {
        sources.push(el.textContent.trim());
      });
      sourcesByPath[key] = sources;
      return;
    }

    // Strategy 2: elements still have the class
    var preElems = document.querySelectorAll("pre.mermaid");

    // Strategy 3: class already removed — scan for keywords
    if (preElems.length === 0) {
      var candidates = [];
      document.querySelectorAll("pre > code").forEach(function (code) {
        if (MERMAID_KW.test(code.textContent.trim())) {
          candidates.push(code.parentElement);
        }
      });
      preElems = candidates;
    }

    Array.prototype.forEach.call(preElems, function (pre) {
      var code = pre.querySelector("code");
      sources.push(code ? code.textContent.trim() : pre.textContent.trim());
    });

    if (sources.length > 0) {
      sourcesByPath[key] = sources;
    }
  }

  // Capture immediately — runs before the theme's async Mermaid processing
  captureSources();

  // Re-capture and re-probe after SPA navigations (Zensical instant loading)
  if (typeof document$ !== "undefined") {
    document$.subscribe(function () {
      captureSources();
      scheduleMermaidProbe();
      applyImageZoomHints();
    });
  } else {
    // Fallback: watch for URL pathname changes
    var lastPath = window.location.pathname;
    var navObserver = new MutationObserver(function () {
      if (window.location.pathname !== lastPath) {
        lastPath = window.location.pathname;
        captureSources();
        scheduleMermaidProbe();
        applyImageZoomHints();
      }
    });
    navObserver.observe(document.body, { childList: true, subtree: true });
  }

  // Initial probes
  scheduleMermaidProbe();
  applyImageZoomHints();

  /* ── Overlay ───────────────────────────────────────────────────────── */

  function getOverlay() {
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.className = "click-zoom-overlay";
    overlay.tabIndex = -1;
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute(
      "aria-label",
      "Zoomed content — click or press Escape to close"
    );

    var hint = document.createElement("button");
    hint.type = "button";
    hint.className = "click-zoom-close";
    hint.setAttribute("aria-label", "Close zoomed content");
    hint.textContent = "Close (Esc)";
    overlay.appendChild(hint);

    overlay.addEventListener("click", function (event) {
      if (event.target === overlay || event.target === hint) {
        closeOverlay();
      }
    });

    return overlay;
  }

  function fixSvgWidth(container) {
    var svg = container.querySelector("svg");
    if (!svg) return;

    // Mermaid 11 produces SVGs with width="100%" and inline
    // style="max-width: Xpx". Inside a flex container "100%" has no
    // intrinsic size, so the SVG collapses. Promote the max-width
    // pixel value to the actual width.
    var mw = svg.style.maxWidth;
    if (mw && mw.endsWith("px")) {
      svg.style.width = mw;
      svg.style.maxWidth = "100%";
    }
  }

  function getFocusableElements(root) {
    return Array.prototype.slice
      .call(
        root.querySelectorAll(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )
      )
      .filter(function (el) {
        return !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
      });
  }

  function focusOverlay() {
    if (!overlay) return;

    var focusables = getFocusableElements(overlay);
    var target = focusables[0] || overlay;
    if (target && target.focus) {
      target.focus();
    }
  }

  function restoreFocus() {
    if (!lastFocusedElement || !lastFocusedElement.focus) return;

    try {
      lastFocusedElement.focus({ preventScroll: true });
    } catch (_) {
      lastFocusedElement.focus();
    }
  }

  function sanitizeSvgNode(svgEl) {
    ["script", "foreignObject", "iframe", "object", "embed"].forEach(
      function (selector) {
        svgEl.querySelectorAll(selector).forEach(function (el) {
          el.remove();
        });
      }
    );

    var all = [svgEl].concat(
      Array.prototype.slice.call(svgEl.querySelectorAll("*"))
    );

    all.forEach(function (el) {
      Array.prototype.slice.call(el.attributes).forEach(function (attr) {
        var name = attr.name.toLowerCase();
        var value = attr.value.trim();

        if (name.indexOf("on") === 0) {
          el.removeAttribute(attr.name);
          return;
        }

        if (
          (name === "href" || name === "xlink:href") &&
          /^javascript:/i.test(value)
        ) {
          el.removeAttribute(attr.name);
        }
      });
    });

    return svgEl;
  }

  /**
   * Parse SVG from a trusted Mermaid re-render.
   *
   * Uses innerHTML (lenient HTML parser) instead of DOMParser with
   * image/svg+xml.  Mermaid flowcharts emit <foreignObject> containing
   * HTML elements like <br> (void, not self-closing) which is valid HTML
   * but invalid XML — the strict XML parser would reject it.
   *
   * No sanitisation needed: mermaid.render() output is trusted
   * (client-side renderer, not user-supplied markup).
   */
  function mermaidSvgToElement(svgText) {
    var wrapper = document.createElement("div");
    wrapper.innerHTML = svgText;
    var svg = wrapper.querySelector("svg");
    return svg || null;
  }

  /**
   * Parse SVG from an external source (fetched URL).
   *
   * Uses strict XML parsing + sanitisation because the content is
   * not under our control.
   */
  function parseSvgMarkup(svgText) {
    var parser = new DOMParser();
    var doc = parser.parseFromString(svgText, "image/svg+xml");

    if (doc.getElementsByTagName("parsererror").length > 0) {
      return null;
    }

    var svgEl = doc.documentElement;
    if (!svgEl || svgEl.nodeName.toLowerCase() !== "svg") {
      return null;
    }

    sanitizeSvgNode(svgEl);
    return document.importNode(svgEl, true);
  }

  function openOverlayWithContent(contentEl, triggerEl) {
    var el = getOverlay();
    var prev = el.querySelector(".click-zoom-content");
    if (prev) prev.remove();

    var container = document.createElement("div");
    container.className = "click-zoom-content";
    container.appendChild(contentEl);

    fixSvgWidth(container);

    el.appendChild(container);
    document.body.appendChild(el);
    lastFocusedElement =
      triggerEl && triggerEl.focus
        ? triggerEl
        : document.activeElement && document.activeElement.focus
          ? document.activeElement
          : null;
    void el.offsetWidth;
    el.classList.add("active");
    prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    focusOverlay();
  }

  function closeOverlay() {
    if (!overlay) return;

    overlay.classList.remove("active");
    document.body.style.overflow = prevOverflow;

    function removeOverlay() {
      if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
      restoreFocus();
    }

    var fallback = setTimeout(removeOverlay, 300);
    overlay.addEventListener(
      "transitionend",
      function handler() {
        overlay.removeEventListener("transitionend", handler);
        clearTimeout(fallback);
        removeOverlay();
      },
      { once: true }
    );
  }

  /* ── Mermaid zoomability probing ───────────────────────────────────── */

  /**
   * Probe-render each diagram to determine its natural SVG width.
   * Diagrams that already fit at full size within their container get
   * .click-zoom-excluded so the CSS cursor hint is suppressed.
   *
   * Adopted from the proven cosalette mermaid-zoom.js approach:
   * poll for the mermaid global and .mermaid containers, then probe.
   */
  var pendingPoll = null;

  function scheduleMermaidProbe() {
    if (pendingPoll) {
      clearTimeout(pendingPoll);
      pendingPoll = null;
    }

    var attempts = 0;

    function attempt() {
      pendingPoll = null;

      // Wait for the mermaid runtime and rendered containers to appear
      if (
        typeof mermaid === "undefined" ||
        document.querySelectorAll(".mermaid").length === 0
      ) {
        if (++attempts < 50) pendingPoll = setTimeout(attempt, 200);
        return;
      }

      // Brief settling delay so Mermaid finishes rendering all diagrams
      pendingPoll = setTimeout(markMermaidZoomable, 300);
    }

    attempt();
  }

  function markMermaidZoomable() {
    var path = window.location.pathname;
    var containers = document.querySelectorAll(".mermaid");
    var sources = sourcesByPath[path];
    if (!containers.length || !sources) return;

    Array.prototype.forEach.call(containers, function (container, index) {
      if (index >= sources.length) return;

      var id = "__click_zoom_probe_" + renderCounter++;
      mermaid
        .render(id, sources[index])
        .then(function (result) {
          if (window.location.pathname !== path) return;

          // Clean up temporary elements Mermaid may leave behind
          var temp = document.getElementById(id);
          if (temp) temp.remove();
          temp = document.getElementById("d" + id);
          if (temp) temp.remove();

          // Parse the SVG to extract its natural (max-width) dimension
          var svg = mermaidSvgToElement(result.svg);
          if (!svg) return;

          var naturalWidth = 0;
          var mw = svg.style.maxWidth;
          if (mw && mw.endsWith("px")) {
            naturalWidth = parseFloat(mw);
          } else {
            var w = svg.getAttribute("width");
            if (w && /^[\d.]+px$/.test(w)) naturalWidth = parseFloat(w);
          }
          if (naturalWidth <= 0) return;

          if (naturalWidth <= container.clientWidth) {
            container.classList.add("click-zoom-excluded");
          } else {
            container.classList.remove("click-zoom-excluded");
          }
        })
        .catch(function () {
          // Probe failed — leave zoom enabled (safe default)
        });
    });
  }

  /* ── Image / inline SVG zoom hints ─────────────────────────────────── */

  var ZOOM_THRESHOLD = 8;
  var IMAGE_SELECTORS = 'article img[src$=".svg"], article figure img';

  function wouldBenefitFromZoom(el) {
    var renderedWidth = el.getBoundingClientRect().width;

    if (el.tagName === "IMG") {
      if (el.naturalWidth === 0) return true;
      return el.naturalWidth > renderedWidth + ZOOM_THRESHOLD;
    }

    return true;
  }

  /**
   * Set [data-click-zoom] on content images that would benefit from
   * zooming. Uses a targeted selector to avoid matching theme icon SVGs.
   */
  function applyImageZoomHints() {
    try {
      document.querySelectorAll(IMAGE_SELECTORS).forEach(function (el) {
        if (wouldBenefitFromZoom(el)) {
          el.setAttribute("data-click-zoom", "");
        }
      });
    } catch (_) {
      // Invalid selector — skip silently
    }
  }

  /* ── Click handling (event delegation) ─────────────────────────────── */

  /**
   * Walk up from the click target to find a .mermaid container.
   * Returns the container index among all .mermaid elements, or -1.
   */
  function findMermaidIndex(target) {
    var el = target;
    for (var i = 0; i < 10 && el && el !== document.body; i++) {
      if (el.classList && el.classList.contains("mermaid")) {
        if (el.classList.contains("click-zoom-excluded")) return -1;
        var all = document.querySelectorAll(".mermaid");
        return Array.prototype.indexOf.call(all, el);
      }
      el = el.parentElement;
    }
    return -1;
  }

  /**
   * Walk up from the click target to find an element matching
   * [data-click-zoom] for non-Mermaid content (images, inline SVGs).
   */
  function findZoomableAncestor(target) {
    var el = target;
    for (var i = 0; i < 15 && el && el !== document.body; i++) {
      if (el.hasAttribute && el.hasAttribute("data-click-zoom")) return el;
      el = el.parentElement;
    }
    return null;
  }

  document.addEventListener(
    "click",
    function (event) {
      if (overlay && overlay.classList.contains("active")) return;

      // Phase 1: Mermaid diagrams (opt-out — zoom by default)
      var mermaidIndex = findMermaidIndex(event.target);
      if (mermaidIndex >= 0) {
        var sources = sourcesByPath[window.location.pathname];
        if (sources && mermaidIndex < sources.length) {
          if (typeof mermaid === "undefined") return;

          event.preventDefault();
          event.stopPropagation();

          var id = "__click_zoom_mermaid_" + renderCounter++;
          mermaid
            .render(id, sources[mermaidIndex])
            .then(function (result) {
              // Clean up temporary elements mermaid.render() leaves behind
              var temp = document.getElementById(id);
              if (temp) temp.remove();
              temp = document.getElementById("d" + id);
              if (temp) temp.remove();

              var svgEl = mermaidSvgToElement(result.svg);
              if (!svgEl) throw new Error("Mermaid returned invalid SVG");
              openOverlayWithContent(svgEl, event.target);
            })
            .catch(function (err) {
              console.error("[click-zoom] Mermaid render failed:", err);
            });
          return;
        }
      }

      // Phase 2: Images and inline SVGs (opt-in via [data-click-zoom])
      var matched = findZoomableAncestor(event.target);
      if (!matched) return;

      event.preventDefault();
      event.stopPropagation();

      if (matched.tagName === "IMG") {
        fetchAndDisplay(matched.src, matched);
        return;
      }

      var svg =
        matched.tagName === "svg" ? matched : matched.querySelector("svg");
      if (svg) {
        cloneAndDisplay(svg, matched);
      }
    },
    true
  );

  /* ── Display helpers ───────────────────────────────────────────────── */

  function cloneAndDisplay(svgEl, triggerEl) {
    var clone = svgEl.cloneNode(true);
    openOverlayWithContent(clone, triggerEl);
  }

  function fetchAndDisplay(src, triggerEl) {
    if (src.toLowerCase().endsWith(".svg") || src.indexOf(".svg") !== -1) {
      fetch(src)
        .then(function (response) {
          if (!response.ok) throw new Error("Fetch failed: " + response.status);
          return response.text();
        })
        .then(function (svgText) {
          var svgEl = parseSvgMarkup(svgText);
          if (!svgEl) throw new Error("Invalid SVG response");
          openOverlayWithContent(svgEl, triggerEl);
        })
        .catch(function () {
          displayAsImg(src, triggerEl);
        });
      return;
    }

    displayAsImg(src, triggerEl);
  }

  function displayAsImg(src, triggerEl) {
    var img = document.createElement("img");
    img.src = src;
    img.alt = "Zoomed image";
    openOverlayWithContent(img, triggerEl);
  }

  /* ── Keyboard handling ─────────────────────────────────────────────── */

  document.addEventListener("keydown", function (event) {
    if (!overlay || !overlay.classList.contains("active")) return;

    if (event.key === "Escape") {
      closeOverlay();
      return;
    }

    if (event.key !== "Tab") return;

    var focusables = getFocusableElements(overlay);
    if (focusables.length === 0) {
      event.preventDefault();
      overlay.focus();
      return;
    }

    var first = focusables[0];
    var last = focusables[focusables.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
      return;
    }

    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });
})();
