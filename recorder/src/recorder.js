/**
 * BotFlow Recorder — Injected JS for element capture.
 * Adds a floating toolbar and captures element selectors on click.
 */
(function () {
  'use strict';

  if (window.__botflow_recorder) return;
  window.__botflow_recorder = true;

  const API_BASE = window.__botflow_api || '';
  let selectMode = false;
  let extractMode = false;
  let stepCount = 0;
  let hoveredEl = null;

  // --- Toolbar ---
  const toolbar = document.createElement('div');
  toolbar.id = 'botflow-toolbar';
  toolbar.innerHTML = `
    <div style="
      position: fixed; top: 10px; right: 10px; z-index: 999999;
      background: rgba(30, 30, 46, 0.95); color: #cdd6f4;
      padding: 10px 16px; border-radius: 10px;
      font-family: system-ui, sans-serif; font-size: 13px;
      display: flex; gap: 8px; align-items: center;
      box-shadow: 0 4px 20px rgba(0,0,0,0.4);
      backdrop-filter: blur(8px);
    ">
      <span style="font-weight: bold; margin-right: 4px;">BotFlow</span>
      <button id="bf-select" style="cursor:pointer;padding:4px 10px;border:1px solid #585b70;border-radius:6px;background:#313244;color:#cdd6f4;">Select</button>
      <button id="bf-extract" style="cursor:pointer;padding:4px 10px;border:1px solid #585b70;border-radius:6px;background:#313244;color:#cdd6f4;">Extract</button>
      <button id="bf-done" style="cursor:pointer;padding:4px 10px;border:1px solid #a6e3a1;border-radius:6px;background:#313244;color:#a6e3a1;">Done</button>
      <span id="bf-count" style="
        background: #89b4fa; color: #1e1e2e;
        padding: 2px 8px; border-radius: 10px;
        font-weight: bold; min-width: 20px; text-align: center;
      ">0</span>
    </div>
  `;
  document.body.appendChild(toolbar);

  const btnSelect = document.getElementById('bf-select');
  const btnExtract = document.getElementById('bf-extract');
  const btnDone = document.getElementById('bf-done');
  const countBadge = document.getElementById('bf-count');

  btnSelect.addEventListener('click', function (e) {
    e.stopPropagation();
    selectMode = !selectMode;
    extractMode = false;
    btnSelect.style.background = selectMode ? '#89b4fa' : '#313244';
    btnSelect.style.color = selectMode ? '#1e1e2e' : '#cdd6f4';
    btnExtract.style.background = '#313244';
    btnExtract.style.color = '#cdd6f4';
  });

  btnExtract.addEventListener('click', function (e) {
    e.stopPropagation();
    extractMode = !extractMode;
    selectMode = false;
    btnExtract.style.background = extractMode ? '#f9e2af' : '#313244';
    btnExtract.style.color = extractMode ? '#1e1e2e' : '#cdd6f4';
    btnSelect.style.background = '#313244';
    btnSelect.style.color = '#cdd6f4';
  });

  btnDone.addEventListener('click', function (e) {
    e.stopPropagation();
    selectMode = false;
    extractMode = false;
    btnSelect.style.background = '#313244';
    btnExtract.style.background = '#313244';
  });

  // --- CSS Selector generation ---
  function generateSelector(el) {
    if (el.id) return '#' + el.id;
    var testid = el.getAttribute('data-testid');
    if (testid) return '[data-testid="' + testid + '"]';
    var name = el.getAttribute('name');
    if (name) return el.tagName.toLowerCase() + '[name="' + name + '"]';
    var classes = Array.from(el.classList).filter(function (c) {
      return !c.startsWith('bf-');
    });
    if (classes.length > 0) {
      var sel = el.tagName.toLowerCase() + '.' + classes.join('.');
      if (document.querySelectorAll(sel).length === 1) return sel;
    }
    // Fallback: nth-child
    var parent = el.parentElement;
    if (parent) {
      var children = Array.from(parent.children);
      var idx = children.indexOf(el) + 1;
      var ptag = parent.tagName.toLowerCase();
      return ptag + ' > ' + el.tagName.toLowerCase() + ':nth-child(' + idx + ')';
    }
    return el.tagName.toLowerCase();
  }

  // --- XPath generation ---
  function generateXPath(el) {
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

  // --- Action inference ---
  function inferAction(el) {
    var tag = el.tagName.toLowerCase();
    if (tag === 'input' || tag === 'textarea') return 'fill';
    if (tag === 'select') return 'select';
    if (tag === 'a' || tag === 'button') return 'click';
    if (el.getAttribute('role') === 'button') return 'click';
    return 'click';
  }

  // --- Highlight ---
  document.addEventListener(
    'mouseover',
    function (e) {
      if (!selectMode && !extractMode) return;
      if (toolbar.contains(e.target)) return;
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

  // --- Capture ---
  document.addEventListener(
    'click',
    function (e) {
      if (!selectMode && !extractMode) return;
      if (toolbar.contains(e.target)) return;

      e.preventDefault();
      e.stopPropagation();

      var el = e.target;
      var action = extractMode ? 'extract' : inferAction(el);
      var rect = el.getBoundingClientRect();

      var data = {
        action: action,
        target: {
          css: generateSelector(el),
          xpath: generateXPath(el),
          text_content: (el.textContent || '').trim().substring(0, 100),
          aria_label: el.getAttribute('aria-label') || null,
          tag_name: el.tagName.toLowerCase(),
          bounding_box: {
            x: Math.round(rect.x),
            y: Math.round(rect.y),
            width: Math.round(rect.width),
            height: Math.round(rect.height),
          },
        },
        url: window.location.href,
      };

      // Flash green
      el.style.outline = '3px solid #a6e3a1';
      setTimeout(function () {
        el.style.outline = '';
      }, 500);

      // Send to API
      fetch(API_BASE + '/api/capture-step', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      })
        .then(function (r) {
          return r.json();
        })
        .then(function (result) {
          stepCount = result.step_count || stepCount + 1;
          countBadge.textContent = stepCount;
        })
        .catch(function (err) {
          console.error('BotFlow capture error:', err);
        });
    },
    true
  );
})();
