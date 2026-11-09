/**
 * KINDRED MOTION — PORTAL INTERACTIONS (portal-motion.js)
 * Genie effect on pairing requests, match collision celebration overlay,
 * match cards dealt-hand entry, FLIP filter transitions, and status stickers.
 */

(function () {
  'use strict';

  let reqCount = 0;

  function initPortalMotion() {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    // 1. Inject Matched Moment Overlay (if not present)
    ensureMomentOverlay();

    // 2. Intercept "send request" buttons for signature Genie Effect
    document.addEventListener('click', async (e) => {
      const sendBtn = e.target.closest('[data-s]');
      if (!sendBtn || sendBtn.disabled || sendBtn.dataset.genieHandled) return;

      const card = sendBtn.closest('.pc') || sendBtn.closest('.card');
      if (!card) return;

      // Play genie animation before API call finishes
      await playGenieEffect(card, sendBtn);
    });

    // 3. Intercept "accept" request buttons for Match Moment Celebration
    document.addEventListener('click', async (e) => {
      const acceptBtn = e.target.closest('[data-a]');
      if (!acceptBtn) return;

      const card = acceptBtn.closest('.rq-card') || acceptBtn.closest('.card') || acceptBtn.closest('.pc');
      const partnerName = card ? (card.querySelector('h3, .who h3, b') || {}).textContent || 'Roommate' : 'Roommate';
      const userAvatar = (document.querySelector('.nb-avatar, .user-pill') || {}).textContent || 'U';

      // Play celebration overlay
      setTimeout(() => {
        triggerMatchMoment(userAvatar, partnerName);
      }, 350);
    });

    // 4. Staggered Entry for Match Cards
    observeMatchCards(reduced);

    // 5. Status Stickers Physics
    initStatusStickers(km, reduced);
  }

  // Signature Genie Effect: Clones card, funnels into navbar requests link
  async function playGenieEffect(card, btn) {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    // Target navbar requests link
    const targetLink = document.querySelector('[data-go="requests"]') || document.querySelector('#nav-matches') || document.querySelector('.nav-actions');
    if (!targetLink || reduced) return;

    btn.disabled = true;
    btn.classList.add('btn-pending-wobble');
    btn.textContent = 'request pending...';

    const r = card.getBoundingClientRect();
    const t = targetLink.getBoundingClientRect();

    const clone = card.cloneNode(true);
    clone.style.cssText = `
      position: fixed;
      left: ${r.left}px;
      top: ${r.top}px;
      width: ${r.width}px;
      height: ${r.height}px;
      margin: 0;
      z-index: 18000;
      pointer-events: none;
      transform-origin: 50% 100%;
    `;
    document.body.appendChild(clone);

    const dx = t.left + t.width / 2 - (r.left + r.width / 2);
    const dy = t.top + t.height / 2 - r.bottom;

    const full = 'polygon(-14% -14%, 114% -14%, 114% 114%, -14% 114%)';
    const f1 = 'polygon(0% 0%, 100% 0%, 64% 100%, 36% 100%)';
    const f2 = 'polygon(41% 0%, 59% 0%, 52% 100%, 48% 100%)';

    const anim = clone.animate(
      [
        { transform: 'translate(0, 0) scale(1, 1)', clipPath: full, offset: 0 },
        { transform: 'translate(0, 14px) scale(1.08, 0.88)', clipPath: full, offset: 0.16 },
        { transform: `translate(${dx * 0.16}px, ${dy * 0.12}px) scale(0.8, 0.95) skewX(-6deg)`, clipPath: f1, offset: 0.42 },
        { transform: `translate(${dx * 0.6}px, ${dy * 0.62}px) scale(0.4, 0.5) skewX(10deg)`, clipPath: f1, offset: 0.75 },
        { transform: `translate(${dx}px, ${dy}px) scale(0.04, 0.04) skewX(0deg)`, clipPath: f2, offset: 1 }
      ],
      { duration: km ? km.D(950) : 950, easing: 'cubic-bezier(.6, .05, .3, 1)', fill: 'forwards' }
    );

    // Source card press reaction
    card.animate(
      [{ transform: 'scale(1)' }, { transform: 'scale(0.96)' }, { transform: 'scale(1)' }],
      { duration: 320 }
    );

    await anim.finished.catch(() => {});
    clone.remove();
    reqCount++;

    // Target navbar bounce + pink +1 badge pop
    targetLink.animate(
      [
        { transform: 'scale(1) rotate(0deg)' },
        { transform: 'scale(1.3) rotate(-6deg)', offset: 0.5 },
        { transform: 'scale(1) rotate(0deg)' }
      ],
      { duration: 450, easing: 'cubic-bezier(.34, 1.56, .64, 1)' }
    );

    let badge = targetLink.querySelector('.badge');
    if (!badge) {
      badge = document.createElement('span');
      badge.className = 'badge';
      targetLink.appendChild(badge);
    }
    badge.textContent = reqCount;
    badge.animate(
      [
        { transform: 'scale(0)' },
        { transform: 'scale(1.6)', offset: 0.5 },
        { transform: 'scale(1)' }
      ],
      { duration: 500, easing: 'cubic-bezier(.34, 1.56, .64, 1)', fill: 'forwards' }
    );

    // Burst confetti & stars at navbar link
    const targetCenterX = t.left + t.width / 2;
    const targetCenterY = t.top + t.height / 2;
    if (km) {
      km.starBurst(targetCenterX, targetCenterY, 8);
      km.confetti(targetCenterX, targetCenterY, 24, Math.PI * 2, -Math.PI / 2, 9);
    }
  }

  // Full-Screen Match Moment Collision Celebration Overlay
  function ensureMomentOverlay() {
    if (document.getElementById('moment')) return;

    const ov = document.createElement('div');
    ov.id = 'moment';
    ov.setAttribute('role', 'dialog');
    ov.setAttribute('aria-modal', 'true');
    ov.innerHTML = `
      <div class="stage" id="m-stage">
        <div class="big-av" id="m-you">U</div>
        <div class="big-av" id="m-them">P</div>
        <div class="hit" id="m-hit" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="90" height="90">
            <path d="M12 1C13 8 16 11 23 12C16 13 13 16 12 23C11 16 8 13 1 12C8 11 11 8 12 1Z" fill="#FFE27A" stroke="#16121F" stroke-width="1.3" stroke-linejoin="round"/>
          </svg>
        </div>
      </div>
      <div class="stamp-big" id="m-stamp">MATCHED!</div>
      <div id="m-sub">official roommate allotment confirmed ✓</div>
      <button class="btn nb-btn-cream" id="m-close" style="background:#FFF8EA;border:3px solid #16121F;border-radius:999px;padding:10px 28px;font-weight:800;font-size:16px;cursor:pointer">nice!</button>
    `;
    document.body.appendChild(ov);

    function closeMoment() {
      ov.classList.remove('show');
    }

    ov.addEventListener('click', closeMoment);
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && ov.classList.contains('show')) {
        closeMoment();
      }
    });
  }

  async function triggerMatchMoment(youInitial = 'U', themName = 'Roommate') {
    const ov = document.getElementById('moment');
    if (!ov) return;

    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    const L = ov.querySelector('#m-you');
    const R = ov.querySelector('#m-them');
    const S = ov.querySelector('#m-stamp');
    const H = ov.querySelector('#m-hit');
    const sub = ov.querySelector('#m-sub');

    L.textContent = (youInitial || 'U').slice(0, 1).toUpperCase();
    R.textContent = (themName || 'P').slice(0, 1).toUpperCase();
    sub.textContent = `u + ${themName} · 100% mutual match ✓`;

    S.style.opacity = '0';
    H.style.opacity = '0';
    ov.classList.add('show');

    if (!reduced) {
      // Avatars slide in from sides and collide
      const aL = L.animate(
        [
          { transform: 'translateX(-70vw) rotate(-45deg)' },
          { transform: 'translateX(22px) rotate(8deg)', offset: 0.7 },
          { transform: 'translateX(0) rotate(0deg)' }
        ],
        { duration: 720, easing: 'cubic-bezier(.5, 0, .3, 1)', fill: 'forwards' }
      );

      const aR = R.animate(
        [
          { transform: 'translateX(70vw) rotate(45deg)' },
          { transform: 'translateX(-22px) rotate(-8deg)', offset: 0.7 },
          { transform: 'translateX(0) rotate(0deg)' }
        ],
        { duration: 720, easing: 'cubic-bezier(.5, 0, .3, 1)', fill: 'forwards' }
      );

      await aL.finished.catch(() => {});

      // Hit spark effect
      H.animate(
        [
          { opacity: 1, transform: 'scale(0) rotate(0deg)' },
          { opacity: 1, transform: 'scale(2.5) rotate(120deg)', offset: 0.5 },
          { opacity: 0, transform: 'scale(3.5) rotate(220deg)' }
        ],
        { duration: 650, fill: 'forwards' }
      );

      // Stamp slams down
      S.animate(
        [
          { opacity: 0, transform: 'scale(3.2) rotate(-22deg)' },
          { opacity: 1, transform: 'scale(0.92) rotate(-6deg)', offset: 0.65 },
          { opacity: 1, transform: 'scale(1) rotate(-6deg)' }
        ],
        { duration: 500, easing: 'cubic-bezier(.2, .9, .3, 1)', fill: 'forwards' }
      );

      // Page shakes
      if (km) {
        km.shake(document.body, 12);
        km.shake(ov, 8);
        const sr = ov.querySelector('#m-stage').getBoundingClientRect();
        const mx = sr.left + sr.width / 2;
        const my = sr.top + sr.height / 2;

        // Triple confetti burst: center + both bottom corners
        km.confetti(mx, my, 110, Math.PI * 2, -Math.PI / 2, 18);
        setTimeout(() => {
          km.confetti(window.innerWidth * 0.15, window.innerHeight, 60, 0.9, -Math.PI / 3, 22);
          km.confetti(window.innerWidth * 0.85, window.innerHeight, 60, 0.9, (-Math.PI * 2) / 3, 22);
        }, 320);
      }
    } else {
      S.style.opacity = '1';
    }
  }

  // Dealt-card entry for match cards (.pc)
  function observeMatchCards(reduced) {
    const km = window.KindredMotion;
    const observer = new MutationObserver(() => {
      const cards = document.querySelectorAll('.pc:not(.pc-animated)');
      cards.forEach((card, i) => {
        card.classList.add('pc-animated');

        if (!reduced) {
          card.animate(
            [
              { opacity: 0, transform: `translate(${(1.5 - (i % 4)) * 140}px, -80px) rotate(${((i % 4) - 1.5) * -22}deg) scale(0.6)` },
              { opacity: 1, transform: 'translate(0, 0) scale(1)' }
            ],
            {
              duration: 720,
              delay: i * 110,
              easing: 'cubic-bezier(.3, 1.35, .5, 1)',
              fill: 'backwards'
            }
          );
        }

        // Count up score %
        const scoreEl = card.querySelector('.sc');
        if (scoreEl && km) {
          const val = parseInt(scoreEl.textContent, 10);
          if (!isNaN(val)) {
            scoreEl.innerHTML = `<span class="score-num">0</span><small>/100</small>`;
            const span = scoreEl.querySelector('.score-num');
            setTimeout(() => {
              km.countTo(span, 0, val, 900);
            }, i * 110 + 200);
          }
        }
      });
    });

    const app = document.getElementById('app') || document.body;
    observer.observe(app, { childList: true, subtree: true });
  }

  // Status Stickers: wobbles, confetti on click/view, nope shake
  function initStatusStickers(km, reduced) {
    document.addEventListener('click', (e) => {
      const matchedSticker = e.target.closest('.st-ok, .chip.g, [data-status="matched"]');
      if (matchedSticker && km) {
        const r = matchedSticker.getBoundingClientRect();
        km.confetti(r.left + r.width / 2, r.top, 50, Math.PI * 1.2, -Math.PI / 2, 13);
        km.starBurst(r.left + r.width / 2, r.top, 8);
      }

      const rejectedSticker = e.target.closest('.st-no, .chip.r, [data-status="rejected"]');
      if (rejectedSticker) {
        rejectedSticker.classList.remove('shake-head');
        void rejectedSticker.offsetWidth;
        rejectedSticker.classList.add('shake-head');
      }
    });
  }

  window.KindredPortalMotion = {
    triggerMatchMoment,
    playGenieEffect
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initPortalMotion);
  } else {
    initPortalMotion();
  }
})();
