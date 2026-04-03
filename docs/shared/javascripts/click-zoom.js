// SPDX-FileCopyrightText: 2026 ff-fab
// SPDX-License-Identifier: MIT

/* click-zoom — Click-to-fullscreen zoom for diagrams, SVGs, and images ---- */
/*                                                                             */
/* Strategies:                                                                 */
/*   1. RE-RENDER — Mermaid diagrams behind closed Shadow DOM                  */
/*   2. FETCH     — <img> elements (SVG fetched inline, raster as <img>)       */
/*   3. CLONE     — Inline <svg> elements via cloneNode(true)                  */

;(function () {
  "use strict";

  var overlay = null;
  var prevOverflow = "";
  var lastFocusedElement = null;
  var sourcesByPath = {};
  var probeGeneration = 0;
  var probeCache = {};
  var selectors = window.__clickZoomSelectors || [
    ".mermaid",
    "article svg",
    'article img[src$=".svg"]',
  ];
  var MERMAID_KW =
    /^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|erDiagram|journey|gantt|pie|gitgraph|mindmap|timeline|quadrantChart|sankey|xychart)\b/i;

  var hasMermaidSelector = selectors.some(function (selector) {
    return selector.indexOf(".mermaid") !== -1;
  });

  function captureSources() {
    if (!hasMermaidSelector) return;

    var key = window.location.pathname;
    if (sourcesByPath[key]) return;

    var sources = [];
    var preElems = document.querySelectorAll("pre.mermaid");
    var preservedSources = document.querySelectorAll(
      "script.click-zoom-mermaid-source[type='text/plain']"
    );

    if (preservedSources.length > 0) {
      preservedSources.forEach(function (el) {
        sources.push(el.textContent.trim());
      });
      sourcesByPath[key] = sources;
      return;
    }

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

  captureSources();

  function onPageChange() {
    captureSources();
    probeGeneration++;
    applyZoomHints();
  }

  if (typeof document$ !== "undefined") {
    document$.subscribe(function () {
      onPageChange();
    });
  } else {
    var lastPath = window.location.pathname;
    var navObserver = new MutationObserver(function () {
      if (window.location.pathname !== lastPath) {
        lastPath = window.location.pathname;
        onPageChange();
      }
    });
    navObserver.observe(document.body, { childList: true, subtree: true });
  }

  var ZOOM_THRESHOLD = 8;

  function wouldBenefitFromZoom(el) {
    var renderedWidth = el.getBoundingClientRect().width;

    if (el.tagName === "IMG") {
      if (el.naturalWidth === 0) return true;
      return el.naturalWidth > renderedWidth + ZOOM_THRESHOLD;
    }

    if (el.tagName === "svg" || el.tagName === "SVG") {
      var maxWidth = el.style.maxWidth;
      if (maxWidth && maxWidth.endsWith("px")) {
        return parseFloat(maxWidth) > renderedWidth + ZOOM_THRESHOLD;
      }

      var widthAttr = el.getAttribute("width");
      if (widthAttr && !widthAttr.endsWith("%")) {
        var width = parseFloat(widthAttr);
        if (!isNaN(width)) return width > renderedWidth + ZOOM_THRESHOLD;
      }

      return true;
    }

    return true;
  }

  function applyMermaidZoomHints(generation) {
    if (typeof mermaid === "undefined") return;

    var sources = sourcesByPath[window.location.pathname];
    if (!sources || sources.length === 0) return;

    var mermaidEls = document.querySelectorAll(".mermaid");

    var chain = Promise.resolve();
    Array.prototype.forEach.call(mermaidEls, function (el, index) {
      chain = chain.then(function () {
        if (generation !== probeGeneration) return;

        var source = sources[index];
        if (!source) {
          el.setAttribute("data-click-zoom", "");
          return;
        }

        // Mermaid diagrams stay more usable when zoom is always available.
        // Width probing can under-detect sequence diagrams whose rendered width
        // is constrained by the layout even though the content remains dense.
        el.setAttribute("data-click-zoom", "");

        if (Object.prototype.hasOwnProperty.call(probeCache, source)) {
          return;
        }

        var probeId = "__click_zoom_probe_" + generation + "_" + index;

        return mermaid
          .render(probeId, source)
          .then(function (result) {
            if (generation !== probeGeneration) return;

            var stray = document.getElementById(probeId);
            if (stray && stray.parentNode) stray.parentNode.removeChild(stray);

            var naturalWidth = 0;
            var maxWidthMatch = result.svg.match(/max-width:\s*([\d.]+)px/);
            if (maxWidthMatch) naturalWidth = parseFloat(maxWidthMatch[1]);

            if (naturalWidth === 0) {
              var viewBoxMatch = result.svg.match(
                /viewBox="[\d.\-]+\s+[\d.\-]+\s+([\d.]+)/
              );
              if (viewBoxMatch) naturalWidth = parseFloat(viewBoxMatch[1]);
            }

            probeCache[source] = naturalWidth;
          })
          .catch(function () {
            if (generation !== probeGeneration) return;
            var stray = document.getElementById(probeId);
            if (stray && stray.parentNode) stray.parentNode.removeChild(stray);
            probeCache[source] = 0;
            el.setAttribute("data-click-zoom", "");
          });
      });
    });
  }

  function waitForMermaidThenProbe(generation) {
    if (document.querySelectorAll(".mermaid").length === 0) return;

    var sources = sourcesByPath[window.location.pathname];
    if (!sources || sources.length === 0) return;

    var attempts = 0;

    function poll() {
      if (generation !== probeGeneration) return;

      var ready =
        typeof mermaid !== "undefined" &&
        document.querySelectorAll(".mermaid code").length === 0;

      if (ready) {
        applyMermaidZoomHints(generation);
        return;
      }

      if (++attempts >= 60) {
        if (generation !== probeGeneration) return;
        document.querySelectorAll(".mermaid").forEach(function (el) {
          el.setAttribute("data-click-zoom", "");
        });
        return;
      }

      setTimeout(poll, 100);
    }

    poll();
  }

  function applyZoomHints() {
    var combined = selectors.join(", ");
    try {
      document.querySelectorAll(combined).forEach(function (el) {
        if (el.classList && el.classList.contains("mermaid")) return;
        if (wouldBenefitFromZoom(el)) {
          el.setAttribute("data-click-zoom", "");
        }
      });
    } catch (_) {
      return;
    }

    if (hasMermaidSelector) {
      waitForMermaidThenProbe(probeGeneration);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyZoomHints);
  } else {
    applyZoomHints();
  }

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

    var maxWidth = svg.style.maxWidth;
    if (maxWidth && maxWidth.endsWith("px")) {
      svg.style.width = maxWidth;
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

  var renderCounter = 0;

  function reRenderMermaid(el) {
    var sources = sourcesByPath[window.location.pathname];
    if (!sources) return;

    var all = document.querySelectorAll(".mermaid");
    var index = Array.prototype.indexOf.call(all, el);
    if (index < 0 || index >= sources.length) return;
    if (typeof mermaid === "undefined") return;

    var id = "__click_zoom_mermaid_" + renderCounter++;
    var source = sources[index];

    mermaid
      .render(id, source)
      .then(function (result) {
        var svgEl = parseSvgMarkup(result.svg);
        if (!svgEl) throw new Error("Mermaid returned invalid SVG");
        openOverlayWithContent(svgEl, el);
      })
      .catch(function (err) {
        console.error("[click-zoom] Mermaid render failed:", err);
      });
  }

  function findMatchingAncestor(target, sels) {
    var combined = sels.join(", ");
    var el = target;

    for (var i = 0; i < 15 && el && el !== document.body; i++) {
      try {
        if (el.matches && el.matches(combined)) return el;
      } catch (_) {
        break;
      }
      el = el.parentElement;
    }

    return null;
  }

  document.addEventListener(
    "click",
    function (event) {
      if (overlay && overlay.classList.contains("active")) return;

      var mermaidMatch =
        event.target &&
        event.target.closest &&
        event.target.closest(".mermaid");
      var matched =
        mermaidMatch && mermaidMatch.hasAttribute("data-click-zoom")
          ? mermaidMatch
          : findMatchingAncestor(event.target, selectors);
      if (!matched) return;
      if (!matched.hasAttribute("data-click-zoom")) return;

      event.preventDefault();
      event.stopPropagation();

      if (
        matched.classList.contains("mermaid") &&
        sourcesByPath[window.location.pathname]
      ) {
        reRenderMermaid(matched);
        return;
      }

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

  document.addEventListener("keydown", function (event) {
    if (!overlay || !overlay.classList.contains("active")) return;

    if (event.key === "Escape" && overlay && overlay.classList.contains("active")) {
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
