/**
 * KINDRED MOTION — EASTER EGG (easter-egg.js)
 * Clicking the logo 5 times within 3s rains stars down the screen.
 */

(function () {
  'use strict';

  function initEasterEgg() {
    const logo = document.querySelector('.brand') || document.querySelector('#logo');
    if (!logo) return;

    let clicks = [];

    logo.addEventListener('click', (e) => {
      const now = performance.now();
      clicks = clicks.filter((t) => now - t < 3000);
      clicks.push(now);

      // Mini logo star jiggle on every click
      const dred = logo.querySelector('.brand-title span') || logo.querySelector('.logo-mark');
      if (dred && window.KindredMotion && !window.KindredMotion.isReduced()) {
        dred.animate(
          [
            { transform: 'scale(1) rotate(0deg)' },
            { transform: 'scale(1.25) rotate(-12deg)' },
            { transform: 'scale(0.9) rotate(8deg)' },
            { transform: 'scale(1) rotate(0deg)' }
          ],
          { duration: 400, easing: 'cubic-bezier(.34, 1.56, .64, 1)' }
        );
      }

      if (clicks.length >= 5) {
        clicks = [];
        rainStars();
      }
    });
  }

  function rainStars() {
    if (window.KindredMotion) {
      window.KindredMotion.toast('✨ stars. everywhere. ✨');
    }
    if (window.KindredMotion && window.KindredMotion.isReduced()) return;

    const colors = ['#CDB8FF', '#D4FF4F', '#FF5FA2', '#FFE27A', '#B8F5CF', '#FFF8EA'];
    const totalStars = 70;

    for (let i = 0; i < totalStars; i++) {
      const star = document.createElement('div');
      star.className = 'fx-star motion-star';
      const c = colors[i % colors.length];
      const s = 16 + Math.random() * 24;
      star.innerHTML = `<svg viewBox="0 0 24 24" width="${s}" height="${s}" aria-hidden="true">
        <path d="M12 1C13 8 16 11 23 12C16 13 13 16 12 23C11 16 8 13 1 12C8 11 11 8 12 1Z" fill="${c}" stroke="#16121F" stroke-width="1.6" stroke-linejoin="round"/>
      </svg>`;
      document.body.appendChild(star);

      const startX = Math.random() * window.innerWidth;
      const drift = (Math.random() - 0.5) * 160;
      const dur = 1800 + Math.random() * 1600;
      const delay = Math.random() * 900;

      const anim = star.animate(
        [
          { transform: `translate(${startX}px, -60px) rotate(0deg)`, opacity: 1 },
          { transform: `translate(${startX + drift}px, ${window.innerHeight + 80}px) rotate(${360 + Math.random() * 540}deg)`, opacity: 0.9 }
        ],
        {
          duration: dur,
          delay: delay,
          easing: 'cubic-bezier(.4, 0, .8, .6)',
          fill: 'backwards'
        }
      );

      anim.onfinish = () => star.remove();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initEasterEgg);
  } else {
    initEasterEgg();
  }
})();
