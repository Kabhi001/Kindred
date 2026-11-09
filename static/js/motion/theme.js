/**
 * KINDRED MOTION — DARK THEME & VIEW TRANSITIONS (theme.js)
 * Circular reveal from click point with View Transitions API.
 * Preserves palette, updates background, text, outline, and shadow tokens.
 * Persists in localStorage with try/catch.
 */

(function () {
  'use strict';

  function initTheme() {
    // Read saved theme
    try {
      const saved = localStorage.getItem('kindred-theme');
      if (saved) {
        document.documentElement.dataset.theme = saved;
      }
    } catch (e) {}

    const toggleBtn = document.getElementById('theme-toggle');
    if (!toggleBtn) return;

    toggleBtn.addEventListener('click', (e) => {
      const current = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      const rect = toggleBtn.getBoundingClientRect();
      const x = rect.left + rect.width / 2;
      const y = rect.top + rect.height / 2;

      setThemeWithReveal(next, x, y);
    });
  }

  function setThemeWithReveal(nextTheme, x = window.innerWidth / 2, y = 30) {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    const apply = () => {
      document.documentElement.dataset.theme = nextTheme;
      try {
        localStorage.setItem('kindred-theme', nextTheme);
      } catch (e) {}
    };

    if (!document.startViewTransition || reduced) {
      apply();
      return;
    }

    const r = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
    const transition = document.startViewTransition(apply);

    transition.ready.then(() => {
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${r}px at ${x}px ${y}px)`
          ]
        },
        {
          duration: 720,
          easing: 'cubic-bezier(.6, .05, .2, 1)',
          pseudoElement: '::view-transition-new(root)'
        }
      );
    }).catch(() => {});
  }

  window.KindredTheme = {
    setThemeWithReveal
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTheme);
  } else {
    initTheme();
  }
})();
