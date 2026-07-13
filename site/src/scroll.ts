import { gsap } from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import Lenis from 'lenis';
import type { SceneHandle } from './scene';

gsap.registerPlugin(ScrollTrigger);

export function initScroll(scene: SceneHandle) {
  const nav = document.getElementById('nav');

  const lenis = new Lenis({
    lerp: 0.1,
    smoothWheel: true,
    wheelMultiplier: 1,
  });

  lenis.on('scroll', ScrollTrigger.update);
  lenis.on('scroll', ({ scroll }: { scroll: number }) => {
    nav?.classList.toggle('is-stuck', scroll > 40);
  });

  gsap.ticker.add((time) => lenis.raf(time * 1000));
  gsap.ticker.lagSmoothing(0);

  // Drive the WebGL narrative from the scroll position over the pinned stage.
  const narrative = document.querySelector('.narrative');
  if (narrative) {
    ScrollTrigger.create({
      trigger: narrative,
      start: 'top top',
      end: 'bottom bottom',
      scrub: true,
      onUpdate: (self) => scene.setProgress(self.progress),
    });
  }

  // Smooth anchor links through Lenis.
  document.querySelectorAll<HTMLAnchorElement>('a[href^="#"]').forEach((a) => {
    a.addEventListener('click', (e) => {
      const id = a.getAttribute('href');
      if (!id || id === '#') return;
      const target = document.querySelector(id);
      if (target) {
        e.preventDefault();
        lenis.scrollTo(target as HTMLElement, { offset: -60 });
      }
    });
  });

  ScrollTrigger.refresh();
}
