(() => {
  'use strict';
  const root = document.documentElement;
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const cards = [...document.querySelectorAll('.feature-card, .showcase-card')];
  const running = true;
  root.dataset.motion = 'running';
  let scrollFrame = 0;
  let pointerFrame = 0;
  let pointerTarget = null;
  let pointerPosition = null;

  function resetCard(card) {
    card.style.removeProperty('--tilt-x');
    card.style.removeProperty('--tilt-y');
    card.style.removeProperty('--pointer-x');
    card.style.removeProperty('--pointer-y');
  }

  const revealTargets = document.querySelectorAll('.section-heading, .feature-card, .showcase-card, .continuity-copy, .project-structure, .steps article, .prompt-card, .faq-heading, .faq-list, .final-cta');
  if ('IntersectionObserver' in window) {
    const hero = document.querySelector('.hero');
    const heroObserver = new IntersectionObserver(entries => {
      hero.classList.toggle('hero-offscreen', !entries[0].isIntersecting);
    });
    heroObserver.observe(hero);
  }
  if (running && 'IntersectionObserver' in window) {
    const revealObserver = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          revealObserver.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08, rootMargin: '0px 0px 24px 0px' });
    revealTargets.forEach(element => {
      const siblings = [...element.parentElement.children];
      const stagger = element.matches('.feature-card, .showcase-card, .steps article') ? siblings.indexOf(element) % 3 : 0;
      element.style.setProperty('--reveal-delay', `${stagger * 70}ms`);
      element.classList.add('reveal-ready');
      revealObserver.observe(element);
    });
    // Keyboard users never focus an invisible control.
    document.addEventListener('focusin', event => {
      const target = event.target.closest('.reveal-ready');
      if (target) target.classList.add('is-visible');
    });
  }

  cards.forEach(card => {
    card.addEventListener('pointermove', event => {
      if (!running || !finePointer.matches || event.pointerType === 'touch') return;
      pointerTarget = card;
      pointerPosition = { x: event.clientX, y: event.clientY };
      if (pointerFrame) return;
      pointerFrame = requestAnimationFrame(() => {
        pointerFrame = 0;
        if (!running || !pointerTarget || !pointerPosition) return;
        const rect = pointerTarget.getBoundingClientRect();
        const x = pointerPosition.x - rect.left;
        const y = pointerPosition.y - rect.top;
        pointerTarget.style.setProperty('--pointer-x', `${x.toFixed(1)}px`);
        pointerTarget.style.setProperty('--pointer-y', `${y.toFixed(1)}px`);
        pointerTarget.style.setProperty('--tilt-x', `${((0.5 - y / rect.height) * 3).toFixed(2)}deg`);
        pointerTarget.style.setProperty('--tilt-y', `${((x / rect.width - 0.5) * 3).toFixed(2)}deg`);
      });
    }, { passive: true });
    card.addEventListener('pointerleave', () => {
      resetCard(card);
      if (pointerTarget === card) pointerTarget = null;
    });
  });

  const navLinks = [...document.querySelectorAll('#navigation a[href^="#"]')];
  const sections = navLinks.map(link => document.querySelector(link.getAttribute('href'))).filter(Boolean);
  function updateScroll() {
    scrollFrame = 0;
    const total = root.scrollHeight - innerHeight;
    const progress = total > 0 ? Math.min(1, Math.max(0, scrollY / total)) : 0;
    root.style.setProperty('--scroll-progress', progress.toFixed(4));
    let activeId = '';
    sections.forEach(section => { if (section.getBoundingClientRect().top <= innerHeight * 0.45) activeId = section.id; });
    navLinks.forEach(link => {
      if (link.getAttribute('href') === `#${activeId}`) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }
  function scheduleScroll() { if (!scrollFrame) scrollFrame = requestAnimationFrame(updateScroll); }
  addEventListener('scroll', scheduleScroll, { passive: true });
  addEventListener('resize', scheduleScroll, { passive: true });
  addEventListener('load', scheduleScroll, { once: true });
  updateScroll();

  document.addEventListener('visibilitychange', () => {
    root.classList.toggle('page-hidden', document.hidden);
    if (document.hidden) {
      cancelAnimationFrame(pointerFrame);
      pointerFrame = 0;
      cards.forEach(resetCard);
    }
  });
})();
