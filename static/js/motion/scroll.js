/**
 * KINDRED MOTION — SCROLL SECTIONS & BLOSSOM GRAPH (scroll.js)
 * Section title stamps, dealt-hand card entry, animated Edmonds' Blossom graph,
 * trading card flip-in for demo portals with copy toast + starburst,
 * and number count-up tweens on scroll.
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

    // 4. Blossom Algorithm Animated SVG Graph
    initBlossomGraph(reduced);

    // 5. Demo Portal Trading Cards Flip-in & Copy Action
    initDemoLogins(km, reduced);
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

  // 4. Animated Edmonds' Blossom Graph
  function initBlossomGraph(reduced) {
    const algoSec = document.getElementById('algorithm');
    if (!algoSec) return;

    // Check if container already exists
    let graphWrap = algoSec.querySelector('.blossom-graph-card');
    if (!graphWrap) {
      graphWrap = document.createElement('div');
      graphWrap.className = 'blossom-graph-card';

      // Insert before the 3-column feature grid
      const grid = algoSec.querySelector('div[style*="grid-template-columns"]');
      if (grid) {
        algoSec.insertBefore(graphWrap, grid);
      } else {
        algoSec.appendChild(graphWrap);
      }
    }

    graphWrap.innerHTML = `
      <div class="blossom-header">
        <span class="nb-chip nb-chip-white" style="font-size:11px;font-weight:800">JACK EDMONDS (1965) GRAPH SOLVER</span>
        <span class="blossom-status-pill">BLOSSOM CONTRACTION ACTIVE</span>
      </div>
      <div class="blossom-canvas-wrap">
        <svg class="blossom-svg" viewBox="0 0 760 300" aria-label="Edmonds' Blossom cycle contraction simulation">
          <!-- Edges -->
          <g class="blossom-edges">
            <line id="e-ab" x1="180" y1="90" x2="310" y2="70" class="b-edge"/>
            <line id="e-bc" x1="310" y1="70" x2="380" y2="150" class="b-edge"/>
            <line id="e-cd" x1="380" y1="150" x2="310" y2="230" class="b-edge"/>
            <line id="e-de" x1="310" y1="230" x2="180" y2="210" class="b-edge"/>
            <line id="e-ea" x1="180" y1="210" x2="180" y2="90" class="b-edge"/>
            <line id="e-bf" x1="310" y1="70" x2="490" y2="90" class="b-edge match"/>
            <line id="e-cg" x1="380" y1="150" x2="560" y2="150" class="b-edge match"/>
            <line id="e-dh" x1="310" y1="230" x2="490" y2="210" class="b-edge match"/>
          </g>

          <!-- Flower Pseudonode Blossom (Petals) -->
          <g id="blossom-flower" class="blossom-flower" transform="translate(272, 150) scale(0)">
            <circle cx="0" cy="0" r="42" fill="#D4FF4F" stroke="#16121F" stroke-width="3.5"/>
            <!-- 5 Petals -->
            <circle cx="0" cy="-42" r="22" fill="#FF5FA2" stroke="#16121F" stroke-width="3"/>
            <circle cx="40" cy="-14" r="22" fill="#FF5FA2" stroke="#16121F" stroke-width="3"/>
            <circle cx="26" cy="36" r="22" fill="#FF5FA2" stroke="#16121F" stroke-width="3"/>
            <circle cx="-26" cy="36" r="22" fill="#FF5FA2" stroke="#16121F" stroke-width="3"/>
            <circle cx="-40" cy="-14" r="22" fill="#FF5FA2" stroke="#16121F" stroke-width="3"/>
            <circle cx="0" cy="0" r="22" fill="#CDB8FF" stroke="#16121F" stroke-width="3"/>
            <text x="0" y="6" text-anchor="middle" font-family="'Bricolage Grotesque', sans-serif" font-weight="800" font-size="13" fill="#16121F">B*</text>
          </g>

          <!-- Graph Nodes -->
          <g class="blossom-nodes">
            <!-- Cycle 5 Nodes -->
            <g id="node-a" class="b-node" transform="translate(180, 90)">
              <circle r="22" fill="#FFF8EA" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">S1</text>
            </g>
            <g id="node-b" class="b-node" transform="translate(310, 70)">
              <circle r="22" fill="#FFF8EA" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">S2</text>
            </g>
            <g id="node-c" class="b-node" transform="translate(380, 150)">
              <circle r="22" fill="#FFF8EA" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">S3</text>
            </g>
            <g id="node-d" class="b-node" transform="translate(310, 230)">
              <circle r="22" fill="#FFF8EA" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">S4</text>
            </g>
            <g id="node-e" class="b-node" transform="translate(180, 210)">
              <circle r="22" fill="#FFF8EA" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">S5</text>
            </g>
            <!-- Matched Peers -->
            <g id="node-f" class="b-node matched" transform="translate(490, 90)">
              <circle r="22" fill="#B8F5CF" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">P1</text>
            </g>
            <g id="node-g" class="b-node matched" transform="translate(560, 150)">
              <circle r="22" fill="#B8F5CF" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">P2</text>
            </g>
            <g id="node-h" class="b-node matched" transform="translate(490, 210)">
              <circle r="22" fill="#B8F5CF" stroke="#16121F" stroke-width="3"/>
              <text y="5" text-anchor="middle" font-weight="800" font-size="13">P3</text>
            </g>
          </g>
        </svg>
      </div>
      <p class="blossom-caption">
        <strong>Edmonds' Blossom Contraction:</strong> Odd-length alternating cycles contract into flower pseudonodes to bypass parity deadlocks and compute the cohort-optimal maximum-weight match.
      </p>
    `;

    if (reduced) return;

    // Loop cycle: drift -> contract to flower blossom -> pause -> expand & match
    const flower = graphWrap.querySelector('#blossom-flower');
    const cycleNodes = graphWrap.querySelectorAll('#node-a, #node-b, #node-c, #node-d, #node-e');
    const matchedEdges = graphWrap.querySelectorAll('.b-edge.match');
    const statusPill = graphWrap.querySelector('.blossom-status-pill');

    let animTimer;
    let isVisible = false;

    const observer = new IntersectionObserver((entries) => {
      isVisible = entries[0].isIntersecting;
      if (isVisible) runBlossomCycle();
      else clearTimeout(animTimer);
    }, { threshold: 0.25 });

    observer.observe(graphWrap);

    function runBlossomCycle() {
      if (!isVisible) return;

      // Phase 1: Reset & Expand (Nodes visible, flower shrunk)
      flower.style.transition = 'transform 0.5s ease-in, opacity 0.3s';
      flower.style.transform = 'translate(272px, 150px) scale(0)';
      flower.style.opacity = '0';

      cycleNodes.forEach((n) => {
        n.style.transition = 'transform 0.5s var(--pop), opacity 0.3s';
        n.style.opacity = '1';
      });

      matchedEdges.forEach((e) => e.classList.remove('active-match'));
      if (statusPill) statusPill.textContent = '1. DETECTING ODD ALTERNATING CYCLE (5-CYCLE)';

      // Phase 2: Contract cycle into Flower Pseudonode
      animTimer = setTimeout(() => {
        if (!isVisible) return;
        if (statusPill) statusPill.textContent = '2. CONTRACTING BLOSSOM PSEUDONODE (B*)';

        cycleNodes.forEach((n) => {
          n.style.transform = 'translate(272px, 150px) scale(0.2)';
          n.style.opacity = '0';
        });

        setTimeout(() => {
          flower.style.transition = 'transform 0.65s var(--pop), opacity 0.3s';
          flower.style.transform = 'translate(272px, 150px) scale(1)';
          flower.style.opacity = '1';

          // Petals spring bounce
          if (window.KindredMotion) {
            window.KindredMotion.shake(flower, 4);
          }
        }, 350);

        // Phase 3: Global Max-Weight Edge Allotment
        animTimer = setTimeout(() => {
          if (!isVisible) return;
          if (statusPill) statusPill.textContent = '3. SOLVING MAXIMUM-WEIGHT MATCHING ✓';
          matchedEdges.forEach((e) => e.classList.add('active-match'));

          // Loop back
          animTimer = setTimeout(runBlossomCycle, 3800);
        }, 2200);

      }, 2600);
    }
  }

  // 5. Demo Logins Trading Cards Flip-in & Copy Action
  function initDemoLogins(km, reduced) {
    const demoCards = document.querySelectorAll('.demo-grid .nb-card');
    if (!demoCards.length) return;

    const credentials = [
      { role: 'Student', id: '12310266', pass: 'demo2026' },
      { role: 'Warden', id: 'WARDEN-01', pass: 'demo2026' },
      { role: 'Admin', id: '10266', pass: 'admin2026' }
    ];

    demoCards.forEach((card, idx) => {
      card.classList.add('demo-trading-card');

      // Inject quick copy badges
      const cred = credentials[idx] || credentials[0];
      const copyBox = document.createElement('div');
      copyBox.className = 'demo-cred-copy';
      copyBox.innerHTML = `
        <span class="cred-pill" data-copy="${cred.id}" data-cursor="copy">
          ID: <b>${cred.id}</b> 📋
        </span>
      `;
      card.appendChild(copyBox);

      // Trading card 3D flip-in
      if (!reduced && km) {
        km.onView(card.parentElement, () => {
          card.animate(
            [
              { opacity: 0, transform: 'perspective(900px) rotateY(-90deg) translateY(30px) scale(0.85)' },
              { opacity: 1, transform: 'perspective(900px) rotateY(12deg) scale(1.03)', offset: 0.72 },
              { opacity: 1, transform: 'perspective(900px) rotateY(0deg) scale(1)' }
            ],
            {
              duration: 750,
              delay: idx * 150,
              easing: 'cubic-bezier(.34, 1.35, .5, 1)',
              fill: 'forwards'
            }
          );
        }, 0.25);
      }

      // Copy Action with Toast and Starburst
      copyBox.addEventListener('click', (e) => {
        const target = e.target.closest('.cred-pill');
        if (!target) return;
        const val = target.dataset.copy;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(val).catch(() => {});
        }

        if (km) {
          km.toast(`copied ${cred.role} ID: ${val}`);
          const r = target.getBoundingClientRect();
          km.starBurst(r.left + r.width / 2, r.top + r.height / 2, 7);
        }

        // Mini button bounce
        target.animate(
          [
            { transform: 'scale(1)' },
            { transform: 'scale(0.92, 1.12)' },
            { transform: 'scale(1.08, 0.94)' },
            { transform: 'scale(1)' }
          ],
          { duration: 320, easing: 'cubic-bezier(.34, 1.56, .64, 1)' }
        );
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initScrollMotion);
  } else {
    initScrollMotion();
  }
})();
