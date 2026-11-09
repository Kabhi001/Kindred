/**
 * KINDRED MOTION — NAVBAR & BUTTONS (nav.js)
 * Spring drop-in entrance, logo squash-pop, scribble hover underlines,
 * sliding pink dot indicator, magnetic button pull, and scroll shadow deepening.
 */

(function () {
  'use strict';

  function initNavbarMotion() {
    const navbar = document.querySelector('.nb-navbar');
    const logoBlock = document.querySelector('.brand-title span');
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    // 1. Navbar spring drop-in
    if (navbar && !reduced) {
      navbar.animate(
        [
          { transform: 'translateY(-60px) scale(0.96)', opacity: 0 },
          { transform: 'translateY(6px) scale(1.02)', opacity: 1, offset: 0.7 },
          { transform: 'translateY(0) scale(1)', opacity: 1 }
        ],
        {
          duration: 750,
          delay: 100,
          easing: 'cubic-bezier(.34, 1.56, .64, 1)',
          fill: 'backwards'
        }
      );
    }

    // 2. Logo lime "dred" squash-and-pop
    if (logoBlock && !reduced) {
      logoBlock.style.display = 'inline-block';
      logoBlock.style.transformOrigin = 'center bottom';
      setTimeout(() => {
        logoBlock.animate(
          [
            { transform: 'scale(1, 1)' },
            { transform: 'scale(1.3, 0.7)', offset: 0.25 },
            { transform: 'scale(0.85, 1.25)', offset: 0.55 },
            { transform: 'scale(1.08, 0.94)', offset: 0.8 },
            { transform: 'scale(1, 1)' }
          ],
          {
            duration: 650,
            easing: 'cubic-bezier(.34, 1.56, .64, 1)'
          }
        );
      }, 700);
    }

    // 3. Nav link scribble underlines & sliding pink dot
    const navMenu = document.querySelector('.nav-menu');
    const navLinks = document.querySelectorAll('.nav-link');

    if (navMenu && navLinks.length) {
      navMenu.style.position = 'relative';

      // Insert sliding indicator dot
      const dot = document.createElement('div');
      dot.className = 'nav-indicator-dot';
      dot.setAttribute('aria-hidden', 'true');
      navMenu.appendChild(dot);

      function moveDotTo(link) {
        if (!link || reduced) return;
        const menuRect = navMenu.getBoundingClientRect();
        const linkRect = link.getBoundingClientRect();
        const x = linkRect.left - menuRect.left + linkRect.width / 2 - 3.5;
        dot.style.opacity = '1';
        dot.style.transform = `translateX(${x}px)`;
      }

      navLinks.forEach((link) => {
        // Add scribble underline SVG
        const scribble = document.createElement('span');
        scribble.className = 'nav-scribble';
        scribble.setAttribute('aria-hidden', 'true');
        scribble.innerHTML = `<svg viewBox="0 0 100 12" preserveAspectRatio="none">
          <path d="M2 7 C 25 3, 50 11, 75 5 S 95 9, 98 6" pathLength="1"/>
        </svg>`;
        link.appendChild(scribble);

        link.addEventListener('pointerenter', () => moveDotTo(link));
      });

      // Position dot at initial active link or first link on hover
      navMenu.addEventListener('pointerleave', () => {
        const activeLink = document.querySelector('.nav-link.active') || navLinks[0];
        if (activeLink) moveDotTo(activeLink);
      });

      // Initialize position
      setTimeout(() => {
        const initial = document.querySelector('.nav-link.active') || navLinks[0];
        if (initial) moveDotTo(initial);
      }, 500);
    }

    // 4. Scroll behavior: hard shadow deepens, pill shrinks slightly
    let lastScrollY = window.scrollY;
    let ticking = false;

    function handleScroll() {
      if (!navbar) return;
      const scrolled = window.scrollY > 35;
      navbar.classList.toggle('scrolled', scrolled);

      // Scroll progress bar
      const docHeight = document.documentElement.scrollHeight - window.innerHeight;
      const progress = docHeight > 0 ? Math.min(100, Math.max(0, (window.scrollY / docHeight) * 100)) : 0;
      document.documentElement.style.setProperty('--scroll-pct', `${progress}%`);
    }

    window.addEventListener('scroll', () => {
      if (!ticking) {
        window.requestAnimationFrame(() => {
          handleScroll();
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
    handleScroll();

    // 5. Button Magnetic Pull (desktop fine pointer only)
    const isFinePointer = window.matchMedia ? window.matchMedia('(hover: hover) and (pointer: fine)').matches : true;
    if (isFinePointer && !reduced) {
      document.addEventListener('pointermove', (e) => {
        const buttons = document.querySelectorAll('.nb-btn, .btn');
        buttons.forEach((btn) => {
          if (btn.disabled) return;
          const r = btn.getBoundingClientRect();
          const cx = r.left + r.width / 2;
          const cy = r.top + r.height / 2;
          const dx = e.clientX - cx;
          const dy = e.clientY - cy;

          // Pull range ~ 45px outside button bounds
          if (Math.abs(dx) < r.width / 2 + 45 && Math.abs(dy) < r.height / 2 + 35) {
            const mx = Math.max(-8, Math.min(8, dx * 0.18));
            const my = Math.max(-6, Math.min(6, dy * 0.22));
            btn.style.setProperty('--mx', `${mx.toFixed(1)}px`);
            btn.style.setProperty('--my', `${my.toFixed(1)}px`);
          } else {
            if (btn.style.getPropertyValue('--mx') !== '0px') {
              btn.style.setProperty('--mx', '0px');
              btn.style.setProperty('--my', '0px');
            }
          }
        });
      });
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initNavbarMotion);
  } else {
    initNavbarMotion();
  }
})();
