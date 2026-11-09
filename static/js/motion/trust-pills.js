/**
 * KINDRED MOTION — TRUST PILLS (trust-pills.js)
 * Staggered pop-in with spring overshoot, self-drawing SVG checkmarks, and wobble on hover.
 */

(function () {
  'use strict';

  function initTrustPills() {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;
    const heroLeft = document.querySelector('.hero-grid > div:first-child');
    if (!heroLeft) return;

    // Target the container of the 3 trust pills
    const trustPills = heroLeft.querySelectorAll('.nb-chip-mint, .nb-chip-lilac, .nb-chip-yellow');
    if (!trustPills.length) return;

    trustPills.forEach((pill, i) => {
      pill.classList.add('trust-pill-motion');

      // Replace text "✓" with self-drawing SVG checkmark
      if (pill.innerHTML.includes('✓')) {
        pill.innerHTML = pill.innerHTML.replace(
          '✓',
          `<svg viewBox="0 0 16 16" width="14" height="14" class="tick-svg" aria-hidden="true">
            <path d="M2.5 8.5 L6 12 L13.5 4" fill="none" stroke="#16121F" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" pathLength="1"/>
          </svg>`
        );
      }

      if (!reduced) {
        // Staggered pop-in with spring overshoot
        pill.style.transform = 'scale(0) rotate(-6deg)';
        pill.style.opacity = '0';

        setTimeout(() => {
          pill.animate(
            [
              { transform: 'scale(0) rotate(-8deg)', opacity: 0 },
              { transform: 'scale(1.15) rotate(3deg)', opacity: 1, offset: 0.65 },
              { transform: 'scale(0.96) rotate(-1deg)', opacity: 1, offset: 0.85 },
              { transform: 'scale(1) rotate(0deg)', opacity: 1 }
            ],
            {
              duration: 650,
              delay: 850 + i * 140,
              easing: 'cubic-bezier(.34, 1.56, .64, 1)',
              fill: 'forwards'
            }
          ).onfinish = () => {
            pill.style.transform = '';
            pill.style.opacity = '';
            // Trigger checkmark draw
            const tick = pill.querySelector('.tick-svg path');
            if (tick) {
              tick.classList.add('draw');
            }
          };
        }, 100);

        // Hover wobble
        pill.addEventListener('pointerenter', () => {
          pill.animate(
            [
              { transform: 'scale(1) rotate(0deg)' },
              { transform: 'scale(1.08) rotate(-3.5deg)', offset: 0.3 },
              { transform: 'scale(1.08) rotate(3.5deg)', offset: 0.65 },
              { transform: 'scale(1) rotate(0deg)' }
            ],
            { duration: 420, easing: 'cubic-bezier(.34, 1.56, .64, 1)' }
          );
        });
      } else {
        const tick = pill.querySelector('.tick-svg path');
        if (tick) tick.classList.add('draw');
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTrustPills);
  } else {
    initTrustPills();
  }
})();
