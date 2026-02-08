/**
 * BotFlow Recorder — Injected JS for element capture.
 *
 * Three modes:
 *   Auto    — records all clicks and input changes transparently (default)
 *   Select  — manual element picking (clicks are intercepted, not performed)
 *   Extract — manual text extraction (clicks are intercepted)
 */
(function () {
  'use strict';

  if (window.__botflow_recorder) return;
  window.__botflow_recorder = true;

  const API_BASE = window.__botflow_api || '';
  let autoMode = true;
  let selectMode = false;
  let extractMode = false;
  let stepCount = 0;
  let hoveredEl = null;

  // Dedup: ignore rapid duplicate captures on the same element
  let lastCaptureKey = '';
  let lastCaptureTime = 0;

  // Track fields we've attached blur listeners to
  var trackedInputs = new WeakSet();

  // --- Toolbar (deferred until DOM is ready) ---
  var toolbar = null;
  var btnAuto = null;
  var btnSelect = null;
  var btnExtract = null;
  var countBadge = null;

  function initToolbar() {
    if (toolbar) return; // already initialized
    toolbar = document.createElement('div');
    toolbar.id = 'botflow-toolbar';
    toolbar.innerHTML =
      '<div style="' +
        'position:fixed;top:10px;right:10px;z-index:999999;' +
        'background:rgba(30,30,46,0.95);color:#cdd6f4;' +
        'padding:10px 16px;border-radius:10px;' +
        'font-family:system-ui,sans-serif;font-size:13px;' +
        'display:flex;gap:8px;align-items:center;' +
        'box-shadow:0 4px 20px rgba(0,0,0,0.4);' +
        'backdrop-filter:blur(8px);' +
      '">' +
        '<span style="font-weight:bold;margin-right:4px;">BotFlow</span>' +
        '<button id="bf-auto" style="cursor:pointer;padding:4px 10px;border:1px solid #f38ba8;border-radius:6px;background:#f38ba8;color:#1e1e2e;font-weight:bold;">Auto</button>' +
        '<button id="bf-select" style="cursor:pointer;padding:4px 10px;border:1px solid #585b70;border-radius:6px;background:#313244;color:#cdd6f4;">Select</button>' +
        '<button id="bf-extract" style="cursor:pointer;padding:4px 10px;border:1px solid #585b70;border-radius:6px;background:#313244;color:#cdd6f4;">Extract</button>' +
        '<span id="bf-count" style="' +
          'background:#89b4fa;color:#1e1e2e;' +
          'padding:2px 8px;border-radius:10px;' +
          'font-weight:bold;min-width:20px;text-align:center;' +
        '">0</span>' +
      '</div>';
    document.body.appendChild(toolbar);

    btnAuto = document.getElementById('bf-auto');
    btnSelect = document.getElementById('bf-select');
    btnExtract = document.getElementById('bf-extract');
    countBadge = document.getElementById('bf-count');

    btnAuto.addEventListener('click', function (e) {
      e.stopPropagation();
      autoMode = !autoMode;
      selectMode = false;
      extractMode = false;
      updateButtons();
    });

    btnSelect.addEventListener('click', function (e) {
      e.stopPropagation();
      selectMode = !selectMode;
      autoMode = false;
      extractMode = false;
      updateButtons();
    });

    btnExtract.addEventListener('click', function (e) {
      e.stopPropagation();
      extractMode = !extractMode;
      autoMode = false;
      selectMode = false;
      updateButtons();
    });
  }

  // Init toolbar when DOM is ready
  if (document.body) {
    initToolbar();
  } else {
    document.addEventListener('DOMContentLoaded', initToolbar);
  }

  function updateButtons() {
    if (!btnAuto) return;
    btnAuto.style.background = autoMode ? '#f38ba8' : '#313244';
    btnAuto.style.color = autoMode ? '#1e1e2e' : '#cdd6f4';
    btnAuto.style.borderColor = autoMode ? '#f38ba8' : '#585b70';
    btnSelect.style.background = selectMode ? '#89b4fa' : '#313244';
    btnSelect.style.color = selectMode ? '#1e1e2e' : '#cdd6f4';
    btnExtract.style.background = extractMode ? '#f9e2af' : '#313244';
    btnExtract.style.color = extractMode ? '#1e1e2e' : '#cdd6f4';
  }

  // --- CSS Selector generation ---

  // Build the best short selector for a single element (no ancestry).
  function atomicSelector(el) {
    var tag = el.tagName.toLowerCase();
    if (el.id) return '#' + CSS.escape(el.id);
    var testid = el.getAttribute('data-testid');
    if (testid) return '[data-testid="' + testid + '"]';
    var name = el.getAttribute('name');
    if (name) return tag + '[name="' + CSS.escape(name) + '"]';
    var classes = Array.from(el.classList).filter(function (c) {
      return !c.startsWith('bf-') && c.length > 0;
    });
    if (classes.length > 0) return tag + '.' + classes.map(CSS.escape).join('.');
    return tag;
  }

  // Build a nth-child disambiguator for el among its siblings.
  function nthChild(el) {
    var parent = el.parentElement;
    if (!parent) return '';
    var sameTag = Array.from(parent.children).filter(function (c) {
      return c.tagName === el.tagName;
    });
    if (sameTag.length <= 1) return '';
    return ':nth-child(' + (Array.from(parent.children).indexOf(el) + 1) + ')';
  }

  function generateSelector(el) {
    // 1. Try atomic selector — if unique, use it directly.
    var atom = atomicSelector(el);
    try {
      if (document.querySelectorAll(atom).length === 1) return atom;
    } catch (_) {}

    // 2. Walk up ancestors, building a chain until the selector is unique.
    //    Stop at 6 levels to avoid absurdly long selectors.
    var parts = [];
    var current = el;
    for (var depth = 0; depth < 6 && current && current !== document.body; depth++) {
      var seg = atomicSelector(current) + nthChild(current);
      parts.unshift(seg);
      var candidate = parts.join(' > ');
      try {
        if (document.querySelectorAll(candidate).length === 1) return candidate;
      } catch (_) {}
      current = current.parentElement;
    }

    // 3. Fallback: return the full chain we built (best effort).
    return parts.join(' > ');
  }

  // --- XPath generation ---

  // Absolute XPath (fallback).
  function generateAbsoluteXPath(el) {
    var parts = [];
    var current = el;
    while (current && current.nodeType === Node.ELEMENT_NODE) {
      var tag = current.tagName.toLowerCase();
      if (current.id) {
        parts.unshift('//' + tag + '[@id="' + current.id + '"]');
        return parts.join('/');
      }
      var siblings = current.parentElement
        ? Array.from(current.parentElement.children).filter(function (c) {
            return c.tagName === current.tagName;
          })
        : [current];
      if (siblings.length > 1) {
        var idx = siblings.indexOf(current) + 1;
        parts.unshift(tag + '[' + idx + ']');
      } else {
        parts.unshift(tag);
      }
      current = current.parentElement;
    }
    return '/' + parts.join('/');
  }

  // Find a meaningful text label in an element's direct children (headings,
  // spans with short text, etc.) — used to anchor selectors on context.
  function findBlockLabel(container) {
    // Look for headings or prominent text children
    var candidates = container.querySelectorAll('h1,h2,h3,h4,h5,h6,[class*="title"],[class*="header"],[class*="label"],[class*="Title"],[class*="Header"]');
    for (var i = 0; i < candidates.length; i++) {
      var txt = (candidates[i].textContent || '').trim();
      if (txt.length >= 3 && txt.length <= 80) return txt;
    }
    // Also check direct children with short, distinctive text
    for (var j = 0; j < container.children.length; j++) {
      var child = container.children[j];
      var childTag = child.tagName.toLowerCase();
      if (childTag === 'script' || childTag === 'style') continue;
      var ctxt = (child.textContent || '').trim();
      if (ctxt.length >= 3 && ctxt.length <= 40 && child.children.length <= 3) return ctxt;
    }
    return null;
  }

  // Walk up from el to find the nearest ancestor that has a text label (section title).
  // Returns {ancestor, label} or null.
  function findContextualAncestor(el) {
    var current = el.parentElement;
    for (var depth = 0; depth < 8 && current && current !== document.body; depth++) {
      var label = findBlockLabel(current);
      if (label) return { ancestor: current, label: label };
      current = current.parentElement;
    }
    return null;
  }

  // Build a relative XPath from an ancestor down to el.
  function relativeXPath(ancestor, el) {
    var parts = [];
    var current = el;
    while (current && current !== ancestor) {
      var tag = current.tagName.toLowerCase();
      var siblings = current.parentElement
        ? Array.from(current.parentElement.children).filter(function (c) {
            return c.tagName === current.tagName;
          })
        : [current];
      if (siblings.length > 1) {
        var idx = siblings.indexOf(current) + 1;
        parts.unshift(tag + '[' + idx + ']');
      } else {
        parts.unshift(tag);
      }
      current = current.parentElement;
    }
    return parts.join('/');
  }

  // Generate a context-anchored XPath: find the section by its label text,
  // then navigate down to the element.
  function generateXPath(el) {
    var ctx = findContextualAncestor(el);
    if (ctx) {
      var ancTag = ctx.ancestor.tagName.toLowerCase();
      var escaped = ctx.label.replace(/"/g, '\\"');
      var relPath = relativeXPath(ctx.ancestor, el);
      // Build: //*[ancestor-or-self has text "label"]//relative/path
      var anchored = '//' + ancTag + '[.//*[contains(text(),"' + escaped + '")]]/' + relPath;
      // Verify uniqueness
      try {
        var result = document.evaluate(anchored, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
        if (result.snapshotLength === 1) return anchored;
      } catch (_) {}
    }
    // Fallback to absolute
    return generateAbsoluteXPath(el);
  }

  // Collect text labels from ancestor blocks (for dom_neighborhood).
  function collectNeighborhood(el) {
    var labels = [];
    var current = el.parentElement;
    for (var depth = 0; depth < 10 && current && current !== document.body; depth++) {
      var label = findBlockLabel(current);
      if (label && labels.indexOf(label) === -1) labels.push(label);
      current = current.parentElement;
    }
    return labels.length > 0 ? labels.join(' > ') : null;
  }

  // --- Build target payload ---
  function buildTarget(el) {
    var rect = el.getBoundingClientRect();
    return {
      css: generateSelector(el),
      xpath: generateXPath(el),
      text_content: (el.textContent || '').trim().substring(0, 100),
      aria_label: el.getAttribute('aria-label') || null,
      dom_neighborhood: collectNeighborhood(el),
      tag_name: el.tagName.toLowerCase(),
      bounding_box: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
    };
  }

  // --- Action inference ---
  function inferAction(el) {
    var tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea') return 'fill';
    if (tag === 'select') return 'select';
    if (tag === 'a' || tag === 'button') return 'click';
    if (el.getAttribute('role') === 'button') return 'click';
    return 'click';
  }

  // --- Dedup check ---
  function isDuplicate(key) {
    var now = Date.now();
    if (key === lastCaptureKey && now - lastCaptureTime < 500) return true;
    lastCaptureKey = key;
    lastCaptureTime = now;
    return false;
  }

  // --- Send capture to Python via exposed function ---
  function sendCapture(data) {
    // Flash green on the element if we can find it
    try {
      var el = document.querySelector(data.target.css);
      if (el) {
        el.style.outline = '3px solid #a6e3a1';
        setTimeout(function () { el.style.outline = ''; }, 400);
      }
    } catch (_) {}

    // Use the exposed Python function (bypasses CORS/CSP).
    // Falls back to fetch if the bridge isn't available.
    if (typeof window.__botflow_capture === 'function') {
      window.__botflow_capture(JSON.stringify(data))
        .then(function (resultJson) {
          var result = JSON.parse(resultJson);
          stepCount = result.step_count || stepCount + 1;
          if (countBadge) countBadge.textContent = stepCount;
        })
        .catch(function (err) {
          console.error('BotFlow capture error:', err);
        });
    } else {
      fetch(API_BASE + '/api/capture-step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
        .then(function (r) { return r.json(); })
        .then(function (result) {
          stepCount = result.step_count || stepCount + 1;
          if (countBadge) countBadge.textContent = stepCount;
        })
        .catch(function (err) {
          console.error('BotFlow capture error (fetch):', err);
        });
    }
  }

  // --- Highlight (only in Select / Extract mode) ---
  document.addEventListener(
    'mouseover',
    function (e) {
      if (!selectMode && !extractMode) return;
      if (toolbar && toolbar.contains(e.target)) return;
      if (hoveredEl) hoveredEl.style.outline = '';
      hoveredEl = e.target;
      hoveredEl.style.outline = '2px solid #89b4fa';
    },
    true
  );

  document.addEventListener(
    'mouseout',
    function (e) {
      if (hoveredEl) {
        hoveredEl.style.outline = '';
        hoveredEl = null;
      }
    },
    true
  );

  // --- Click capture ---
  document.addEventListener(
    'click',
    function (e) {
      if (toolbar && toolbar.contains(e.target)) return;

      var el = e.target;

      // --- Manual Select / Extract mode: intercept click ---
      if (selectMode || extractMode) {
        e.preventDefault();
        e.stopPropagation();
        var action = extractMode ? 'extract' : inferAction(el);
        sendCapture({
          action: action,
          target: buildTarget(el),
          url: window.location.href,
        });
        return;
      }

      // --- Auto mode: let click through, capture in background ---
      if (!autoMode) return;

      var tag = el.tagName.toLowerCase();
      // In auto mode, skip capturing clicks on input/textarea — those will
      // be captured as fill/type on blur instead.
      if (tag === 'input' || tag === 'textarea' || tag === 'select') {
        // Attach blur listener to capture the value later
        trackInput(el);
        return;
      }

      var key = 'click:' + generateSelector(el);
      if (isDuplicate(key)) return;

      sendCapture({
        action: 'click',
        target: buildTarget(el),
        url: window.location.href,
      });
    },
    true
  );

  // --- Auto mode: track input fields and capture on blur ---
  function trackInput(el) {
    if (trackedInputs.has(el)) return;
    trackedInputs.add(el);

    el.addEventListener('blur', function () {
      if (!autoMode) return;
      var val = el.value || '';
      if (!val) return; // nothing typed, skip

      var key = 'fill:' + generateSelector(el) + ':' + val;
      if (isDuplicate(key)) return;

      sendCapture({
        action: 'fill',
        target: buildTarget(el),
        url: window.location.href,
        value: val,
      });
    });
  }

  // --- Auto mode: also pick up focus on inputs already on the page ---
  document.addEventListener(
    'focusin',
    function (e) {
      if (!autoMode) return;
      var tag = e.target.tagName.toLowerCase();
      if (tag === 'input' || tag === 'textarea' || tag === 'select') {
        trackInput(e.target);
      }
    },
    true
  );
})();
