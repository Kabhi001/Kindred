/**
 * KINDRED MOTION — CALENDAR PHASE (phase.js)
 * Hard-shadow slap slide-in, pulsing live dot on "ACTIVE CYCLE",
 * typewriter text with blinking caret, hover tilt & shadow growth,
 * and dynamic 5-phase progress stepper with bouncing active step.
 */

(function () {
  'use strict';

  function initPhaseCard() {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    // Find the Lime Phase Card in the hero
    const phaseCard = document.querySelector('.hero-grid .nb-card-lime');
    if (!phaseCard) return;

    phaseCard.classList.add('phase-card-motion');

    // 1. Slide-up with Hard-Shadow Slap
    if (!reduced) {
      phaseCard.animate(
        [
          { transform: 'translateY(40px)', opacity: 0, boxShadow: '0 0 0 #16121F' },
          { transform: 'translateY(-5px)', opacity: 1, boxShadow: '8px 8px 0 #16121F', offset: 0.7 },
          { transform: 'translateY(0)', opacity: 1, boxShadow: '6px 6px 0 #16121F' }
        ],
        {
          duration: 700,
          delay: 450,
          easing: 'cubic-bezier(.34, 1.56, .64, 1)',
          fill: 'backwards'
        }
      );
    }

    // 2. "ACTIVE CYCLE" Badge Live Pulsing Dot
    const badge = phaseCard.querySelector('.nb-badge');
    if (badge && !badge.querySelector('.live-pulse-dot')) {
      const dot = document.createElement('span');
      dot.className = 'live-pulse-dot';
      dot.setAttribute('aria-hidden', 'true');
      badge.prepend(dot);
    }

    // 3. Typewriter Effect for Phase Title with Blinking Caret
    const titleEl = phaseCard.querySelector('div[style*="font-size:22px"]');
    if (titleEl) {
      const fullText = titleEl.textContent.trim();
      titleEl.setAttribute('data-full-text', fullText);

      // Parse phase number from text (e.g. "3. Matching Open..." -> 3)
      const match = fullText.match(/^(\d+)\./);
      const currentPhaseNum = match ? parseInt(match[1], 10) : 3;

      if (!reduced) {
        titleEl.innerHTML = '<span class="typed-text"></span><span class="phase-caret">|</span>';
        const typedSpan = titleEl.querySelector('.typed-text');
        let charIdx = 0;

        function typeNext() {
          if (charIdx < fullText.length) {
            typedSpan.textContent += fullText[charIdx];
            charIdx++;
            setTimeout(typeNext, 25);
          }
        }
        setTimeout(typeNext, 650);
      }

      // 4. Progress Stepper (Phases 1 to 5)
      injectPhaseStepper(phaseCard, currentPhaseNum, reduced);
    }

    // 5. Card Hover Tilt & Shadow Growth
    if (!reduced) {
      phaseCard.addEventListener('pointerenter', () => {
        phaseCard.style.transform = 'translate(-2px, -3px) rotate(-1.2deg)';
        phaseCard.style.boxShadow = '10px 10px 0 #16121F';
      });

      phaseCard.addEventListener('pointerleave', () => {
        phaseCard.style.transform = '';
        phaseCard.style.boxShadow = '';
      });
    }
  }

  // Phase Stepper Bar
  function injectPhaseStepper(card, activeNum, reduced) {
    if (card.querySelector('.phase-stepper')) return;

    const stepper = document.createElement('div');
    stepper.className = 'phase-stepper';
    stepper.setAttribute('aria-label', `Academic Phase ${activeNum} of 5`);

    const stepLabels = ['1. Register', '2. Survey', '3. Matching', '4. Freeze', '5. Blossom'];

    for (let i = 1; i <= 5; i++) {
      const step = document.createElement('div');
      step.className = `phase-step ${i === activeNum ? 'active' : i < activeNum ? 'done' : 'upcoming'}`;
      step.setAttribute('title', stepLabels[i - 1]);

      step.innerHTML = `
        <span class="step-dot">${i < activeNum ? '✓' : i}</span>
        ${i < 5 ? '<span class="step-bar"></span>' : ''}
      `;

      if (i === activeNum && !reduced) {
        step.querySelector('.step-dot').classList.add('bouncing-step');
      }

      stepper.appendChild(step);
    }

    card.appendChild(stepper);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPhaseCard);
  } else {
    initPhaseCard();
  }
})();
