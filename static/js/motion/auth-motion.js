/**
 * KINDRED MOTION — AUTH MICRO-INTERACTIONS (auth-motion.js)
 * Springy focus outline, field error shake, and submit button bouncing "..." states.
 */

(function () {
  'use strict';

  function initAuthMotion() {
    const km = window.KindredMotion;
    const reduced = km ? km.isReduced() : false;

    // 1. Focus Outline Reaction on Inputs
    const inputs = document.querySelectorAll('.nb-input, .nb-select, .nb-textarea, input[type="text"], input[type="password"], input[type="email"]');
    inputs.forEach((input) => {
      input.classList.add('motion-input');
    });

    // 2. Intercept Form Submissions to Animate Bouncing "..."
    const forms = document.querySelectorAll('form');
    forms.forEach((form) => {
      const submitBtn = form.querySelector('button[type="submit"]');
      if (!submitBtn) return;

      const originalHTML = submitBtn.innerHTML;

      form.addEventListener('submit', () => {
        // Only if form is valid
        if (form.checkValidity && !form.checkValidity()) {
          // Shake invalid fields
          const invalidEl = form.querySelector(':invalid');
          if (invalidEl && km) km.shake(invalidEl, 8);
          return;
        }

        submitBtn.setAttribute('data-original-html', originalHTML);
        const actionText = submitBtn.textContent.includes('Register') ? 'Registering' : 'Authenticating';
        submitBtn.innerHTML = `<span>${actionText}<span class="dots"><span>.</span><span>.</span><span>.</span></span></span>`;
      });
    });

    // 3. Shake Form on Error Toast
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) {
            if (node.classList.contains('nb-toast-error') || node.classList.contains('err')) {
              const activeForm = document.querySelector('.pane.active form') || document.querySelector('form');
              if (activeForm && km) {
                km.shake(activeForm, 8);
              }
              // Restore button text if submission failed
              const submitBtn = document.querySelector('button[type="submit"]');
              if (submitBtn && submitBtn.getAttribute('data-original-html')) {
                setTimeout(() => {
                  submitBtn.innerHTML = submitBtn.getAttribute('data-original-html');
                }, 500);
              }
            }
          }
        });
      });
    });

    const toastBox = document.getElementById('toast') || document.getElementById('toast-box') || document.body;
    observer.observe(toastBox, { childList: true });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAuthMotion);
  } else {
    initAuthMotion();
  }
})();
