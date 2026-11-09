/**
 * KINDRED MOTION — CUSTOM CURSOR (cursor.js)
 * Desktop with fine pointer only. Chunky pink dot with ink outline that stretches
 * in movement direction, expands over interactive elements, and displays data-cursor labels.
 */

(function () {
  'use strict';

  function initCustomCursor() {
    const isFinePointer = window.matchMedia ? window.matchMedia('(hover: hover) and (pointer: fine)').matches : false;
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    if (!isFinePointer || reduced) return;

    // Create cursor DOM
    let cursor = document.getElementById('motion-cursor');
    if (!cursor) {
      cursor = document.createElement('div');
      cursor.id = 'motion-cursor';
      cursor.setAttribute('aria-hidden', 'true');
      cursor.innerHTML = '<div class="dot"></div><span class="lbl"></span>';
      document.body.appendChild(cursor);
    }

    const dot = cursor.querySelector('.dot');
    const lbl = cursor.querySelector('.lbl');

    document.body.classList.add('has-motion-cursor');

    let mx = window.innerWidth / 2;
    let my = window.innerHeight / 2;
    let x = mx;
    let y = my;
    let scaleFactor = 1;
    let targetScale = 1;
    let isDown = false;
    let currentLabel = '';

    window.addEventListener('pointermove', (e) => {
      mx = e.clientX;
      my = e.clientY;
      cursor.style.opacity = '1';
    }, { passive: true });

    document.addEventListener('pointerleave', () => {
      cursor.style.opacity = '0';
    });

    window.addEventListener('pointerdown', () => { isDown = true; });
    window.addEventListener('pointerup', () => { isDown = false; });

    document.addEventListener('pointerover', (e) => {
      const target = e.target;
      const labeled = target.closest('[data-cursor]');
      const interactive = target.closest('.nb-btn, .btn, .chip, .nb-chip, a, button, input, select, textarea, .theme-toggle-btn, .cred-pill, .matrix-pill');

      if (labeled && labeled.dataset.cursor) {
        currentLabel = labeled.dataset.cursor;
        targetScale = 2.4;
      } else if (interactive) {
        currentLabel = '';
        targetScale = 1.7;
      } else {
        currentLabel = '';
        targetScale = 1;
      }

      lbl.textContent = currentLabel;
      cursor.classList.toggle('has-label', !!currentLabel);
    });

    function renderLoop() {
      // Lerp position
      const nx = x + (mx - x) * 0.26;
      const ny = y + (my - y) * 0.26;
      const vx = nx - x;
      const vy = ny - y;
      x = nx;
      y = ny;

      // Lerp scale
      scaleFactor += (targetScale - scaleFactor) * 0.18;

      // Stretch in direction of velocity
      const speed = Math.hypot(vx, vy);
      const angle = Math.atan2(vy, vx);
      const stretch = Math.min(speed * 0.038, 0.65);
      const pressScale = isDown ? 0.75 : 1;

      cursor.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
      dot.style.transform = `rotate(${angle.toFixed(2)}rad) scale(${(scaleFactor * (1 + stretch) * pressScale).toFixed(2)}, ${(scaleFactor * (1 - stretch * 0.5) * pressScale).toFixed(2)})`;

      requestAnimationFrame(renderLoop);
    }

    requestAnimationFrame(renderLoop);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCustomCursor);
  } else {
    initCustomCursor();
  }
})();
