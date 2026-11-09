/**
 * KINDRED MOTION — HERO LEFT (hero.js)
 * Autonomous tag pop-in & lightning flicker, headline word drop-in & stagger,
 * tilted lilac "random" slot-machine scramble roll settling on "random" with shake,
 * paragraph lime marker highlight draw, CTA button wiggle & arrow/key micro-interactions.
 */

(function () {
  'use strict';

  function initHeroLeft() {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    // 1. Tag pill pop-in + lightning flicker
    const heroTag = document.querySelector('.hero-tag');
    if (heroTag) {
      if (!reduced) {
        heroTag.animate(
          [
            { transform: 'scale(0) rotate(-6deg)', opacity: 0 },
            { transform: 'scale(1.12) rotate(2deg)', opacity: 1, offset: 0.65 },
            { transform: 'scale(1) rotate(0deg)', opacity: 1 }
          ],
          {
            duration: 600,
            delay: 150,
            easing: 'cubic-bezier(.34, 1.56, .64, 1)',
            fill: 'backwards'
          }
        );
      }

      // Lightning flicker
      const lightning = heroTag.querySelector('span');
      if (lightning && !reduced) {
        setInterval(() => {
          lightning.animate(
            [
              { opacity: 1, transform: 'scale(1)' },
              { opacity: 0.2, transform: 'scale(0.85)', offset: 0.2 },
              { opacity: 1, transform: 'scale(1.25)', offset: 0.4 },
              { opacity: 0.3, transform: 'scale(0.9)', offset: 0.6 },
              { opacity: 1, transform: 'scale(1)' }
            ],
            { duration: 450, easing: 'ease-in-out' }
          );
        }, 4200);
      }
    }

    // 2. Headline words drop in + slot-machine roll on "random"
    const heroTitle = document.querySelector('.hero-title');
    if (heroTitle && !reduced) {
      const mark = heroTitle.querySelector('mark');
      const nodes = Array.from(heroTitle.childNodes);
      const words = [];

      nodes.forEach((node) => {
        if (node.nodeType === Node.TEXT_NODE) {
          const parts = node.textContent.split(/(\s+)/);
          parts.forEach((p) => {
            if (p.trim().length > 0) {
              const span = document.createElement('span');
              span.className = 'hero-word';
              span.textContent = p;
              words.push(span);
            } else if (p.length > 0) {
              words.push(document.createTextNode(p));
            }
          });
        } else if (node === mark) {
          words.push(mark);
        } else {
          words.push(node);
        }
      });

      heroTitle.innerHTML = '';
      words.forEach((w) => heroTitle.appendChild(w));

      // Drop in stagger
      const animWords = heroTitle.querySelectorAll('.hero-word');
      animWords.forEach((w, i) => {
        w.style.display = 'inline-block';
        w.animate(
          [
            { transform: 'translateY(-75px) rotate(-8deg)', opacity: 0 },
            { transform: 'translateY(6px) rotate(1.5deg)', opacity: 1, offset: 0.68 },
            { transform: 'translateY(0) rotate(0deg)', opacity: 1 }
          ],
          {
            duration: 700,
            delay: 200 + i * 85,
            easing: 'cubic-bezier(.34, 1.35, .5, 1)',
            fill: 'backwards'
          }
        );
      });

      // Lilac "random" box slot machine scramble roll
      if (mark) {
        initRandomBoxSlot(mark, reduced);
      }
    } else if (heroTitle && reduced) {
      const mark = heroTitle.querySelector('mark');
      if (mark) initRandomBoxSlot(mark, true);
    }

    // 3. Paragraph Lime Marker Highlight
    const heroDesc = document.querySelector('.hero-desc');
    if (heroDesc) {
      const bolds = heroDesc.querySelectorAll('b');
      bolds.forEach((b) => b.classList.add('marker-highlight'));

      if (km && !reduced) {
        km.onView(heroDesc, () => {
          setTimeout(() => {
            bolds.forEach((b, idx) => {
              setTimeout(() => b.classList.add('go'), idx * 280);
            });
          }, 350);
        }, 0.2);
      } else {
        bolds.forEach((b) => b.classList.add('go'));
      }
    }

    // 4. Buttons: Arrow slide + periodic wiggle + Key jiggle
    initCtaButtons(reduced);
  }

  // Slot-machine roll for <mark>random</mark>
  function initRandomBoxSlot(mark, reduced) {
    const slotWords = ['chaotic', 'mystery', 'toxic', 'random'];
    let isRolling = false;

    // Preserve real text for accessibility while animating visual copy
    mark.innerHTML = `
      <span class="sr-only">random</span>
      <span class="random-roller" aria-hidden="true">random</span>
    `;
    const roller = mark.querySelector('.random-roller');

    async function rollWords() {
      if (isRolling || reduced || !roller) return;
      isRolling = true;

      // Animate through sequence
      for (let i = 0; i < slotWords.length; i++) {
        roller.textContent = slotWords[i];
        await roller.animate(
          [
            { transform: 'translateY(-14px)', opacity: 0.3 },
            { transform: 'translateY(2px)', opacity: 1, offset: 0.6 },
            { transform: 'translateY(0)', opacity: 1 }
          ],
          { duration: 180 + i * 40, easing: 'cubic-bezier(.2, .9, .3, 1)' }
        ).finished.catch(() => {});
      }

      // Settle on "random" with a small shake and tilt reaction
      roller.textContent = 'random';
      if (window.KindredMotion) {
        window.KindredMotion.shake(mark, 4);
      }
      isRolling = false;
    }

    // Initial roll after headline drops in
    if (!reduced) {
      setTimeout(rollWords, 900);
      // Re-run on hover
      mark.addEventListener('pointerenter', rollWords);
    }
  }

  // CTA button interactions
  function initCtaButtons(reduced) {
    const heroBtns = document.querySelector('.hero-btns');
    if (!heroBtns) return;

    // Find Primary Action button (find your roommate →)
    const primaryBtn = heroBtns.querySelector('.nb-btn-primary');
    if (primaryBtn) {
      // Wrap arrow in dedicated span for slide
      if (primaryBtn.innerHTML.includes('→')) {
        primaryBtn.innerHTML = primaryBtn.innerHTML.replace(
          '→',
          '<span class="btn-arrow" aria-hidden="true">→</span>'
        );
      }

      // Periodic wiggle every ~4.5s unless hovered
      if (!reduced) {
        setInterval(() => {
          if (!primaryBtn.matches(':hover') && !primaryBtn.matches(':active')) {
            primaryBtn.animate(
              [
                { transform: 'rotate(0deg)' },
                { transform: 'rotate(-4deg) scale(1.05)', offset: 0.25 },
                { transform: 'rotate(4deg) scale(1.05)', offset: 0.5 },
                { transform: 'rotate(-2.5deg)', offset: 0.75 },
                { transform: 'rotate(0deg)' }
              ],
              { duration: 650, easing: 'ease-in-out' }
            );
          }
        }, 4500);
      }
    }

    // Find Secondary / Accent Action button (Sign In to Portal 🔑)
    const accentBtn = heroBtns.querySelector('.nb-btn-accent, .nb-btn-neutral');
    if (accentBtn) {
      if (accentBtn.innerHTML.includes('🔑')) {
        accentBtn.innerHTML = accentBtn.innerHTML.replace(
          '🔑',
          '<span class="btn-key" aria-hidden="true">🔑</span>'
        );
      }

      const keyEl = accentBtn.querySelector('.btn-key');
      if (keyEl && !reduced) {
        accentBtn.addEventListener('pointerenter', () => {
          keyEl.animate(
            [
              { transform: 'rotate(0deg) scale(1)' },
              { transform: 'rotate(-25deg) scale(1.25)', offset: 0.3 },
              { transform: 'rotate(25deg) scale(1.25)', offset: 0.65 },
              { transform: 'rotate(0deg) scale(1)' }
            ],
            { duration: 450, easing: 'cubic-bezier(.34, 1.56, .64, 1)' }
          );
        });
      }
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initHeroLeft);
  } else {
    initHeroLeft();
  }
})();
