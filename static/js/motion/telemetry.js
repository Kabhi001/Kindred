/**
 * KINDRED MOTION — TELEMETRY & RHYTHM WAVE (telemetry.js)
 * Floating 3D card tilt, SVG stroke-dashoffset draw, phase drift with ~6s harmony sync,
 * chart cursor scanline + ink tooltip, pulsing legend dots, and 8-D Matrix fan-out sticker.
 */

(function () {
  'use strict';

  function initTelemetry() {
    window.KindredTelemetryActive = true;
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    const waveCard = document.querySelector('.wave-card');
    const wa = document.getElementById('wa');
    const wb = document.getElementById('wb');
    const cap = document.getElementById('cap');
    const svgWrap = document.querySelector('.wave-svg-wrap');
    const svg = document.getElementById('rh');

    if (!waveCard || !wa || !wb) return;

    // 1. Telemetry card entrance pop-in
    if (!reduced) {
      waveCard.animate(
        [
          { transform: 'translateY(50px) scale(0.92)', opacity: 0 },
          { transform: 'translateY(-6px) scale(1.02)', opacity: 1, offset: 0.7 },
          { transform: 'translateY(0) scale(1)', opacity: 1 }
        ],
        {
          duration: 750,
          delay: 250,
          easing: 'cubic-bezier(.34, 1.56, .64, 1)',
          fill: 'backwards'
        }
      );
    }

    // 2. 3D Tilt on Desktop toward cursor
    const isFinePointer = window.matchMedia ? window.matchMedia('(hover: hover) and (pointer: fine)').matches : true;
    if (isFinePointer && !reduced) {
      const hero = document.querySelector('.hero') || document.body;
      hero.addEventListener('pointermove', (e) => {
        const cr = waveCard.getBoundingClientRect();
        const centerX = cr.left + cr.width / 2;
        const centerY = cr.top + cr.height / 2;
        const dx = (e.clientX - centerX) / (window.innerWidth / 2);
        const dy = (e.clientY - centerY) / (window.innerHeight / 2);

        // Max ~9deg tilt
        const rotY = Math.max(-9, Math.min(9, dx * 9));
        const rotX = Math.max(-9, Math.min(9, -dy * 9));
        waveCard.style.transform = `perspective(900px) rotateY(${rotY.toFixed(1)}deg) rotateX(${rotX.toFixed(1)}deg)`;
      });

      hero.addEventListener('pointerleave', () => {
        waveCard.style.transform = '';
      });
    }

    // 3. Stroke-dashoffset drawing of wave lines on load
    if (!reduced) {
      [wa, wb].forEach((p, idx) => {
        p.style.strokeDasharray = '1000';
        p.style.strokeDashoffset = '1000';
        p.animate(
          [
            { strokeDashoffset: '1000' },
            { strokeDashoffset: '0' }
          ],
          {
            duration: 1100,
            delay: 400 + idx * 250,
            easing: 'cubic-bezier(.34, 1.2, .64, 1)',
            fill: 'forwards'
          }
        ).onfinish = () => {
          p.style.strokeDasharray = '';
          p.style.strokeDashoffset = '';
        };
      });
    }

    // 4. Continuous rhythm wave animation with drift & ~6s harmony sync
    let raf;
    let lastState = '';
    let lastSyncTime = 0;

    function y(x, t, ph, am) {
      const a = x * 0.011 - t * 1.1 + ph;
      return 120 + am * (Math.sin(a) + 0.35 * Math.sin(2 * a + 1)) / 1.35;
    }

    function tick(ms) {
      if (!document.getElementById('wa')) return;
      const t = reduced ? 4.5 : ms / 1000;
      // 6-second divergence and convergence period
      const d = Math.PI * (0.5 + 0.5 * Math.cos((2 * Math.PI * t) / 6));

      let A = '';
      let B = '';
      for (let x = 0; x <= 1000; x += 6) {
        const c = (x ? 'L' : 'M') + x + ' ';
        A += c + y(x, t, 0, 75).toFixed(1) + ' ';
        B += c + y(x, t, d, 65).toFixed(1) + ' ';
      }
      wa.setAttribute('d', A);
      wb.setAttribute('d', B);

      // State determination: divergence vs harmony
      const isHarmonized = d < 0.65;
      const state = d > 2.0 ? 'out of step' : d > 0.65 ? 'finding rhythm...' : 'in natural harmony ✓';

      if (state !== lastState && cap) {
        lastState = state;
        cap.textContent = state;
        cap.classList.toggle('in-sync', isHarmonized);

        // When syncing, trigger harmony reactions: pulse & star burst
        if (isHarmonized && ms - lastSyncTime > 4000) {
          lastSyncTime = ms;
          triggerHarmonySync(cap, svg);
        }
      }

      if (!reduced) raf = requestAnimationFrame(tick);
    }

    if (!reduced) {
      raf = requestAnimationFrame(tick);
    } else {
      tick(4500);
    }

    // 5. Harmony sync pulse & star burst
    function triggerHarmonySync(capEl, svgEl) {
      if (reduced) return;
      // Pulse pill
      capEl.animate(
        [
          { transform: 'scale(1)' },
          { transform: 'scale(1.18)', offset: 0.4 },
          { transform: 'scale(0.96)', offset: 0.75 },
          { transform: 'scale(1)' }
        ],
        { duration: 500, easing: 'cubic-bezier(.34, 1.56, .64, 1)' }
      );

      // Fire starburst at top right of chart
      if (km && svgEl) {
        const r = svgEl.getBoundingClientRect();
        km.starBurst(r.right - 40, r.top + 30, 7);
      }
    }

    // 6. Interactive Scanline & Ink Tooltip on Chart Hover
    if (svgWrap && svg) {
      svgWrap.style.position = 'relative';

      // Create vertical scanline
      const scanLine = document.createElement('div');
      scanLine.className = 'telemetry-scanline';
      scanLine.setAttribute('aria-hidden', 'true');

      // Create Ink Tooltip
      const tooltip = document.createElement('div');
      tooltip.className = 'telemetry-tooltip';
      tooltip.setAttribute('aria-hidden', 'true');
      tooltip.innerHTML = '<span class="t-pink">Sleep 94%</span> · <span class="t-purple">Study 88%</span>';

      svgWrap.appendChild(scanLine);
      svgWrap.appendChild(tooltip);

      svgWrap.addEventListener('pointerenter', () => {
        scanLine.style.opacity = '1';
        tooltip.style.opacity = '1';
      });

      svgWrap.addEventListener('pointerleave', () => {
        scanLine.style.opacity = '0';
        tooltip.style.opacity = '0';
      });

      svgWrap.addEventListener('pointermove', (e) => {
        const rect = svgWrap.getBoundingClientRect();
        const relX = Math.max(10, Math.min(rect.width - 10, e.clientX - rect.left));
        const pctX = (relX / rect.width) * 100;

        scanLine.style.left = `${relX}px`;

        // Tooltip follows scanline with boundary checking
        const tooltipX = Math.max(70, Math.min(rect.width - 70, relX));
        tooltip.style.left = `${tooltipX}px`;

        // Dynamic telemetry sample based on X position
        const sleep = Math.round(82 + Math.sin(pctX * 0.1) * 14);
        const study = Math.round(80 + Math.cos(pctX * 0.08) * 16);
        tooltip.innerHTML = `<span class="t-pink">Sleep ${sleep}%</span> · <span class="t-purple">Study ${study}%</span>`;
      });
    }

    // 7. Legend Dots Pulse in Step with Waves
    const legendDots = waveCard.querySelectorAll('span[style*="border-radius:50%"]');
    if (legendDots.length && !reduced) {
      legendDots.forEach((dot, i) => {
        dot.classList.add('legend-pulse');
        dot.style.animationDelay = `${i * 350}ms`;
      });
    }

    // 8. "8-D Matrix" Sticker Fan-out & Collapse
    initMatrixPill(waveCard, reduced);
  }

  // 8-D Matrix Sticker: Fans out 8 micro dimensions
  function initMatrixPill(card, reduced) {
    const matrixPill = card.querySelector('.nb-chip-white');
    if (!matrixPill) return;

    matrixPill.classList.add('matrix-pill');
    matrixPill.setAttribute('data-cursor', 'matrix');
    matrixPill.title = 'Click to inspect 8 lifestyle dimensions';

    const dimensions = [
      { name: 'sleep', color: '#FF5FA2' },
      { name: 'clean', color: '#D4FF4F' },
      { name: 'study', color: '#CDB8FF' },
      { name: 'noise', color: '#FFE27A' },
      { name: 'social', color: '#B8F5CF' },
      { name: 'food', color: '#FFB4B4' },
      { name: 'guests', color: '#FFC4DC' },
      { name: 'vibe', color: '#D4FF4F' }
    ];

    // Create wrapper for the fanned dots
    const fanContainer = document.createElement('div');
    fanContainer.className = 'matrix-fan';
    fanContainer.setAttribute('aria-hidden', 'true');

    dimensions.forEach((d, idx) => {
      const dot = document.createElement('span');
      dot.className = 'matrix-dot';
      dot.style.backgroundColor = d.color;
      dot.dataset.name = d.name;
      fanContainer.appendChild(dot);
    });

    matrixPill.style.position = 'relative';
    matrixPill.appendChild(fanContainer);

    let isExpanded = false;
    let collapseTimer = null;

    function fanOut() {
      if (isExpanded) return;
      isExpanded = true;
      fanContainer.classList.add('open');

      const dots = fanContainer.querySelectorAll('.matrix-dot');
      dots.forEach((dot, idx) => {
        const total = dots.length;
        // Arc over the pill
        const angle = -Math.PI + (idx / (total - 1)) * Math.PI;
        const radius = 38;
        const tx = Math.cos(angle) * radius;
        const ty = Math.sin(angle) * radius - 10;

        dot.style.transform = `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px) scale(1)`;
        dot.style.opacity = '1';
      });

      clearTimeout(collapseTimer);
      collapseTimer = setTimeout(collapse, 2800);
    }

    function collapse() {
      isExpanded = false;
      fanContainer.classList.remove('open');
      const dots = fanContainer.querySelectorAll('.matrix-dot');
      dots.forEach((dot) => {
        dot.style.transform = 'translate(0, 0) scale(0)';
        dot.style.opacity = '0';
      });
    }

    matrixPill.addEventListener('pointerenter', fanOut);
    matrixPill.addEventListener('click', (e) => {
      e.stopPropagation();
      if (isExpanded) collapse();
      else fanOut();
    });
    matrixPill.addEventListener('pointerleave', () => {
      collapseTimer = setTimeout(collapse, 1200);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTelemetry);
  } else {
    initTelemetry();
  }
})();
