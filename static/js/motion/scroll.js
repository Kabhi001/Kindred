/**
 * KINDRED MOTION — SCROLL SECTIONS (scroll.js)
 * Section title stamps, dealt-hand card entry, and number count-up tweens on scroll.
 */

(function () {
  'use strict';

  function initScrollMotion() {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    // 1. Section Titles "Stamp" In on Scroll
    initSectionStamps(km, reduced);

    // 2. Step Cards & Hostel Cards Dealt-Hand Stagger
    initDealtCards(km, reduced);

    // 3. Number Counter Tweens on Scroll
    initNumberCounters(km, reduced);
  }

  // Section titles stamp in
  function initSectionStamps(km, reduced) {
    const titles = document.querySelectorAll('section h2, .algo-box h2');
    if (!titles.length) return;

    titles.forEach((h2) => {
      h2.classList.add('stamp-ready');

      if (!reduced && km) {
        km.onView(h2, (el) => {
          el.classList.add('stamped');
          el.animate(
            [
              { opacity: 0, transform: 'scale(1.8) rotate(-4deg)' },
              { opacity: 1, transform: 'scale(0.95) rotate(0.8deg)', offset: 0.7 },
              { opacity: 1, transform: 'scale(1) rotate(0deg)' }
            ],
            { duration: 520, easing: 'cubic-bezier(.2, .8, .3, 1)', fill: 'forwards' }
          );

          // Tiny page shake on impact
          const sec = el.closest('section') || el.parentElement;
          setTimeout(() => {
            km.shake(sec, 3);
          }, 380);
        }, 0.35);
      } else {
        h2.classList.add('stamped');
      }
    });
  }

  // Dealt-hand card entry for steps and hostels
  function initDealtCards(km, reduced) {
    const stepCards = document.querySelectorAll('.steps-grid .nb-card');
    const hostelCards = document.querySelectorAll('.hostels-group .nb-card, #campus-hostels .nb-card-cream');

    function animateCardGroup(cards) {
      if (!cards.length) return;

      if (!reduced && km) {
        km.onView(cards[0].parentElement, () => {
          cards.forEach((card, idx) => {
            card.classList.add('dealt-card');
            const rot = (idx % 2 === 0 ? -1 : 1) * (2 + (idx % 3));
            card.animate(
              [
                { opacity: 0, transform: `translateY(45px) rotate(${rot * 2}deg) scale(0.88)` },
                { opacity: 1, transform: `translateY(-4px) rotate(${rot}deg) scale(1.02)`, offset: 0.75 },
                { opacity: 1, transform: `translateY(0) rotate(${rot * 0.5}deg) scale(1)` }
              ],
              {
                duration: 650,
                delay: idx * 90,
                easing: 'cubic-bezier(.34, 1.35, .5, 1)',
                fill: 'forwards'
              }
            );
          });
        }, 0.2);
      }
    }

    animateCardGroup(stepCards);
    animateCardGroup(hostelCards);
  }

  // Number Counter Tweens
  function initNumberCounters(km, reduced) {
    const numEls = document.querySelectorAll('.stat-num');
    if (!numEls.length) return;

    numEls.forEach((el) => {
      const originalText = el.textContent.trim();
      // Extract numeric value, prefix, suffix (e.g. "200+", "1,200", "85")
      const cleanNum = originalText.replace(/[^0-9]/g, '');
      const parsed = parseInt(cleanNum, 10);
      if (isNaN(parsed)) return;

      const hasPlus = originalText.includes('+');
      const hasComma = originalText.includes(',');
      const suffix = hasPlus ? '+' : '';

      if (!reduced && km) {
        km.onView(el, () => {
          km.countTo(el, 0, parsed, 1200, suffix);
          // Post-format with comma if original had comma
          if (hasComma) {
            setTimeout(() => {
              el.textContent = parsed.toLocaleString() + suffix;
            }, 1250);
          }
        }, 0.3);
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScrollMotion);
  } else {
    initScrollMotion();
  }
})();
