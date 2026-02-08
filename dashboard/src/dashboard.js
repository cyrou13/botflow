/**
 * BotFlow Dashboard — minimal JS for htmx interactions.
 * Most interactivity is handled by htmx attributes in templates.
 */
document.addEventListener('htmx:afterSwap', function (event) {
  // Auto-refresh handling: flash updated elements briefly
  if (event.detail.target) {
    event.detail.target.style.transition = 'background-color 0.3s';
    event.detail.target.style.backgroundColor = 'rgba(137, 180, 250, 0.1)';
    setTimeout(function () {
      event.detail.target.style.backgroundColor = '';
    }, 300);
  }
});
