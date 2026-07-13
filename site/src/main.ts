import './style.css';
import { initScene } from './scene';
import { initInteractions } from './interactions';

const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const isTouch = window.matchMedia('(hover: none)').matches;
const lowPower =
  isTouch ||
  (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4) ||
  window.innerWidth < 860;

const canvas = document.getElementById('gl') as HTMLCanvasElement | null;

async function boot() {
  // Interactions (reveals, count-ups, terminal, cards, copy) always run — cheap and progressive.
  initInteractions();

  if (!canvas) return;

  let scene;
  try {
    scene = initScene(canvas, { reducedMotion: prefersReduced, lowPower: Boolean(lowPower) });
  } catch (err) {
    // WebGL unavailable — leave the layout as a clean static fallback.
    console.warn('WebGL scene disabled:', err);
    canvas.style.display = 'none';
    document.querySelector('.stage')?.classList.add('no-gl');
    return;
  }

  // Pointer parallax on desktop.
  if (!isTouch && !prefersReduced) {
    window.addEventListener('mousemove', (e) => {
      const nx = (e.clientX / window.innerWidth) * 2 - 1;
      const ny = (e.clientY / window.innerHeight) * 2 - 1;
      scene.setPointer(nx, -ny);
    });
  }

  if (prefersReduced) {
    // No smooth-scroll / scrub; show a gentle static hero framing.
    scene.setProgress(0);
    const nav = document.getElementById('nav');
    window.addEventListener('scroll', () => {
      nav?.classList.toggle('is-stuck', window.scrollY > 40);
    });
    return;
  }

  // Lazy-load the scroll engine (Lenis + GSAP ScrollTrigger) so first paint stays light.
  const { initScroll } = await import('./scroll');
  initScroll(scene);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
