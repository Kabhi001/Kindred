/**
 * KINDRED MOTION FOUNDATION (core.js)
 * Physical, springy neo-brutalist micro-interaction utilities.
 * Pure Vanilla ES6+, Web Animations API + Canvas + IntersectionObserver.
 * 60fps GPU acceleration (transform, opacity, clip-path).
 */

(function (root, factory) {
  if (typeof define === 'function' && define.amd) {
    define([], factory);
  } else if (typeof module === 'object' && module.exports) {
    module.exports = factory();
  } else {
    root.KindredMotion = factory();
  }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  // 1. Accessibility: prefers-reduced-motion
  const motionQuery = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  let reduced = motionQuery.matches;
  if (motionQuery.addEventListener) {
    motionQuery.addEventListener('change', (e) => { reduced = e.matches; });
  }

  const isReduced = () => reduced;
  const D = (ms) => (reduced ? 1 : ms);
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, reduced ? 1 : ms));

  // 2. Neo-brutalist spring tokens
  const EASING = {
    spring: 'cubic-bezier(.34, 1.56, .64, 1)',
    snap: 'cubic-bezier(.2, .9, .3, 1)',
    softSpring: 'cubic-bezier(.3, 1.2, .5, 1)',
    easeOutCubic: (t) => 1 - Math.pow(1 - t, 3),
    springOvershoot: (t) => {
      const c4 = (2 * Math.PI) / 3;
      return t === 0 ? 0 : t === 1 ? 1 : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;
    }
  };

  const COLORS = ['#CDB8FF', '#D4FF4F', '#FF5FA2', '#FFE27A', '#FFF8EA', '#B8F5D0'];

  // 3. SVG Star Generator
  function makeStarSVG(color = '#D4FF4F', size = 24) {
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true">
      <path d="M12 1C13 8 16 11 23 12C16 13 13 16 12 23C11 16 8 13 1 12C8 11 11 8 12 1Z" fill="${color}" stroke="#16121F" stroke-width="1.6" stroke-linejoin="round"/>
    </svg>`;
  }

  // 4. Confetti Canvas Helper
  let cv = null;
  let cx = null;
  let parts = [];
  let rafId = 0;

  function ensureCanvas() {
    if (!cv && typeof document !== 'undefined') {
      cv = document.getElementById('motion-confetti');
      if (!cv) {
        cv = document.createElement('canvas');
        cv.id = 'motion-confetti';
        cv.setAttribute('aria-hidden', 'true');
        document.body.appendChild(cv);
      }
      cx = cv.getContext('2d');
      sizeCanvas();
      window.addEventListener('resize', sizeCanvas);
    }
    return cx;
  }

  function sizeCanvas() {
    if (!cv || !cx) return;
    const dpr = window.devicePixelRatio || 1;
    cv.width = window.innerWidth * dpr;
    cv.height = window.innerHeight * dpr;
    cx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function confetti(x, y, n = 80, spread = Math.PI * 2, angle = -Math.PI / 2, power = 15) {
    if (reduced || !ensureCanvas()) return;
    const startX = x != null ? x : window.innerWidth / 2;
    const startY = y != null ? y : window.innerHeight / 2;

    for (let i = 0; i < n; i++) {
      const a = angle + (Math.random() - 0.5) * spread;
      const v = power * (0.35 + Math.random() * 0.85);
      parts.push({
        x: startX,
        y: startY,
        vx: Math.cos(a) * v,
        vy: Math.sin(a) * v,
        r: Math.random() * 6,
        vr: (Math.random() - 0.5) * 0.4,
        w: 8 + Math.random() * 9,
        h: 5 + Math.random() * 7,
        c: COLORS[(Math.random() * COLORS.length) | 0],
        shape: (Math.random() * 3) | 0, // 0 = rect, 1 = circle, 2 = 4-point star
        l: 0,
        m: 90 + Math.random() * 60
      });
    }

    if (!rafId) rafId = requestAnimationFrame(tickConfetti);
  }

  function tickConfetti() {
    if (!cx || !cv) return;
    cx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    parts = parts.filter((p) => p.l < p.m);

    for (const p of parts) {
      p.vy += 0.45;
      p.vx *= 0.985;
      p.vy *= 0.985;
      p.x += p.vx;
      p.y += p.vy;
      p.r += p.vr;
      p.l++;

      cx.save();
      const alpha = 1 - Math.max(0, (p.l - p.m * 0.7) / (p.m * 0.3));
      cx.globalAlpha = Math.max(0, alpha);
      cx.translate(p.x, p.y);
      cx.rotate(p.r);
      cx.fillStyle = p.c;
      cx.strokeStyle = '#16121F';
      cx.lineWidth = 2;

      if (p.shape === 0) {
        cx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
        cx.strokeRect(-p.w / 2, -p.h / 2, p.w, p.h);
      } else if (p.shape === 1) {
        cx.beginPath();
        cx.arc(0, 0, p.h * 0.7, 0, Math.PI * 2);
        cx.fill();
        cx.stroke();
      } else {
        const s = p.w * 0.7;
        cx.beginPath();
        cx.moveTo(0, -s);
        cx.quadraticCurveTo(0, 0, s, 0);
        cx.quadraticCurveTo(0, 0, 0, s);
        cx.quadraticCurveTo(0, 0, -s, 0);
        cx.quadraticCurveTo(0, 0, 0, -s);
        cx.fill();
        cx.stroke();
      }
      cx.restore();
    }

    if (parts.length > 0) {
      rafId = requestAnimationFrame(tickConfetti);
    } else {
      rafId = 0;
      cx.clearRect(0, 0, window.innerWidth, window.innerHeight);
    }
  }

  // 5. Star Burst FX (DOM-based bouncy stars)
  function starBurst(x, y, n = 6) {
    if (reduced || typeof document === 'undefined') return;
    const originX = x != null ? x : window.innerWidth / 2;
    const originY = y != null ? y : window.innerHeight / 2;

    for (let i = 0; i < n; i++) {
      const el = document.createElement('div');
      el.className = 'fx-star motion-star';
      el.innerHTML = makeStarSVG(COLORS[(Math.random() * COLORS.length) | 0], 14 + Math.random() * 16);
      document.body.appendChild(el);

      const a = Math.random() * Math.PI * 2;
      const dist = 45 + Math.random() * 65;
      const targetX = originX + Math.cos(a) * dist;
      const targetY = originY + Math.sin(a) * dist;

      const anim = el.animate(
        [
          { transform: `translate(${originX}px, ${originY}px) scale(0.2) rotate(0deg)`, opacity: 1 },
          { transform: `translate(${targetX}px, ${targetY}px) scale(1.1) rotate(180deg)`, opacity: 1, offset: 0.6 },
          { transform: `translate(${targetX * 1.05}px, ${targetY + 25}px) scale(0) rotate(270deg)`, opacity: 0 }
        ],
        { duration: D(750), easing: 'cubic-bezier(.2, .8, .3, 1)', fill: 'forwards' }
      );
      anim.onfinish = () => el.remove();
    }
  }

  // 6. Shake Helper
  function shake(el, amp = 10) {
    if (!el || reduced) return;
    return el.animate(
      [
        { transform: 'translate(0, 0)' },
        { transform: `translate(${-amp}px, ${amp * 0.4}px) rotate(-0.5deg)` },
        { transform: `translate(${amp}px, ${-amp * 0.4}px) rotate(0.5deg)` },
        { transform: `translate(${-amp * 0.5}px, ${amp * 0.25}px)` },
        { transform: 'translate(0, 0)' }
      ],
      { duration: D(380), easing: 'ease-out' }
    );
  }

  // 7. countTo Helper
  function countTo(el, from, to, dur = 900, suffix = '', prefix = '') {
    if (!el) return;
    const startVal = parseFloat(from) || 0;
    const endVal = parseFloat(to) || 0;
    if (reduced) {
      el.textContent = `${prefix}${Math.round(endVal)}${suffix}`;
      return;
    }
    const t0 = performance.now();
    function step(now) {
      const p = Math.min(1, (now - t0) / dur);
      const cur = Math.round(startVal + (endVal - startVal) * EASING.easeOutCubic(p));
      el.textContent = `${prefix}${cur}${suffix}`;
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // 8. onView IntersectionObserver Helper
  function onView(target, callback, threshold = 0.25) {
    if (typeof document === 'undefined') return;
    const elements = typeof target === 'string' ? Array.from(document.querySelectorAll(target)) : Array.isArray(target) ? target : [target];
    if (!elements.length) return;

    if (!('IntersectionObserver' in window)) {
      elements.forEach((el) => callback(el));
      return;
    }

    const obs = new IntersectionObserver((entries, observer) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          observer.unobserve(entry.target);
          callback(entry.target);
        }
      });
    }, { threshold });

    elements.forEach((el) => obs.observe(el));
    return obs;
  }

  // 9. Toast Notification (Ink Pill with Lime Border)
  let toastTimer = null;
  function toast(msg, type = 'ok') {
    if (typeof document === 'undefined') return;
    let t = document.getElementById('motion-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'motion-toast';
      t.setAttribute('role', 'status');
      t.setAttribute('aria-live', 'polite');
      document.body.appendChild(t);
    }

    const icon = type === 'err' ? '⚠️' : type === 'info' ? '⚡' : '✨';
    t.innerHTML = `<span class="toast-icon">${icon}</span><span>${msg}</span>`;
    t.className = type === 'err' ? 'err show' : 'show';

    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      t.classList.remove('show');
    }, 2800);
  }

  // 10. CSRF Token Helper
  function getCsrfToken() {
    if (typeof document === 'undefined' || !document.cookie) return '';
    const cookies = document.cookie.split(';');
    for (let c of cookies) {
      const [k, v] = c.trim().split('=');
      if (k === 'csrftoken') return decodeURIComponent(v || '');
    }
    return '';
  }

  return {
    isReduced,
    D,
    wait,
    EASING,
    confetti,
    starBurst,
    shake,
    countTo,
    onView,
    toast,
    getCsrfToken,
    makeStarSVG
  };
});
