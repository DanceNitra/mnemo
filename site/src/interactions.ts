import { gsap } from 'gsap';

const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const isTouch = window.matchMedia('(hover: none)').matches;

/* ---------- Reveal on scroll ---------- */
function initReveals(onReveal: (el: Element) => void) {
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          e.target.classList.add('in');
          onReveal(e.target);
          io.unobserve(e.target);
        }
      }
    },
    { threshold: 0.18, rootMargin: '0px 0px -8% 0px' },
  );
  document.querySelectorAll('.reveal').forEach((el) => io.observe(el));
}

/* ---------- Count-up numbers ---------- */
function countUp(el: HTMLElement) {
  const target = parseFloat(el.dataset.count || '0');
  const decimals = parseInt(el.dataset.decimals || '0', 10);
  if (prefersReduced) {
    el.textContent = target.toFixed(decimals);
    return;
  }
  const obj = { v: 0 };
  gsap.to(obj, {
    v: target,
    duration: 1.6,
    ease: 'power2.out',
    onUpdate: () => {
      el.textContent = obj.v.toFixed(decimals);
    },
  });
}

/* ---------- Benchmark bars ---------- */
function drawBench(bench: HTMLElement) {
  bench.classList.add('in');
  bench.querySelectorAll<HTMLElement>('.bench__row').forEach((row) => {
    const v = parseFloat(row.dataset.value || '0');
    const lo = parseFloat(row.dataset.lo || '0');
    const hi = parseFloat(row.dataset.hi || '0');
    const fill = row.querySelector<HTMLElement>('.bench__fill')!;
    const ci = row.querySelector<HTMLElement>('.bench__ci')!;
    // scale: values are on a 0..1 axis
    requestAnimationFrame(() => {
      fill.style.width = `${Math.max(v * 100, 0.5)}%`;
      ci.style.left = `${lo * 100}%`;
      ci.style.width = `${Math.max((hi - lo) * 100, 1)}%`;
    });
  });
}

/* ---------- Auto-typing terminal ---------- */
type Seg = { text: string; cls?: string };
const TERM_LINES: Seg[][] = [
  [{ text: '>>> ', cls: 'prompt' }, { text: 'm.remember("db region is us-east", key="db::region")' }],
  [
    { text: '>>> ', cls: 'prompt' },
    { text: 'm.remember("db region is eu-west", key="db::region")   ' },
    { text: '# correction', cls: 'comment' },
  ],
  [{ text: '>>> ', cls: 'prompt' }, { text: 'm.recall("region")' }],
  [{ text: 'eu-west', cls: 'out' }, { text: '            # the corrected value; the stale one is retired', cls: 'comment' }],
  [{ text: '' }],
  [{ text: '>>> ', cls: 'prompt' }, { text: 'm.route("actually, go back to what we had")' }],
  [
    { text: 'authorization_required', cls: 'err' },
    { text: '   # the content path can’t mint a revert', cls: 'comment' },
  ],
];

function typeTerminal(host: HTMLElement) {
  if (prefersReduced) {
    // Render instantly.
    for (const line of TERM_LINES) {
      for (const seg of line) {
        const s = document.createElement('span');
        if (seg.cls) s.className = seg.cls;
        s.textContent = seg.text;
        host.appendChild(s);
      }
      host.appendChild(document.createTextNode('\n'));
    }
    return;
  }
  const cursor = document.createElement('span');
  cursor.className = 'cursor';
  host.appendChild(cursor);

  let li = 0;
  let si = 0;
  let ci = 0;
  let current: HTMLElement | null = null;

  function step() {
    if (li >= TERM_LINES.length) return;
    const line = TERM_LINES[li];
    if (si >= line.length) {
      host.insertBefore(document.createTextNode('\n'), cursor);
      li++;
      si = 0;
      ci = 0;
      current = null;
      setTimeout(step, 220);
      return;
    }
    const seg = line[si];
    if (!current) {
      current = document.createElement('span');
      if (seg.cls) current.className = seg.cls;
      host.insertBefore(current, cursor);
    }
    if (ci < seg.text.length) {
      current.textContent += seg.text[ci];
      ci++;
      const isPrompt = seg.cls === 'prompt';
      setTimeout(step, isPrompt ? 8 : 16 + Math.random() * 26);
    } else {
      si++;
      ci = 0;
      current = null;
      setTimeout(step, 40);
    }
  }
  setTimeout(step, 400);
}

/* ---------- Magnetic buttons ---------- */
function initMagnetic() {
  if (isTouch || prefersReduced) return;
  document.querySelectorAll<HTMLElement>('.magnetic').forEach((el) => {
    el.addEventListener('mousemove', (e) => {
      const r = el.getBoundingClientRect();
      const mx = e.clientX - (r.left + r.width / 2);
      const my = e.clientY - (r.top + r.height / 2);
      gsap.to(el, { x: mx * 0.28, y: my * 0.4, duration: 0.5, ease: 'power3.out' });
    });
    el.addEventListener('mouseleave', () => {
      gsap.to(el, { x: 0, y: 0, duration: 0.6, ease: 'elastic.out(1, 0.4)' });
    });
  });
}

/* ---------- Spotlight + tilt cards ---------- */
function initCards() {
  if (isTouch || prefersReduced) return;
  document.querySelectorAll<HTMLElement>('.card.spotlight').forEach((card) => {
    card.addEventListener('mousemove', (e) => {
      const r = card.getBoundingClientRect();
      const px = (e.clientX - r.left) / r.width;
      const py = (e.clientY - r.top) / r.height;
      card.style.setProperty('--mx', `${px * 100}%`);
      card.style.setProperty('--my', `${py * 100}%`);
      const rx = (py - 0.5) * -6;
      const ry = (px - 0.5) * 8;
      gsap.to(card, { rotateX: rx, rotateY: ry, duration: 0.4, ease: 'power2.out', transformPerspective: 900 });
    });
    card.addEventListener('mouseleave', () => {
      gsap.to(card, { rotateX: 0, rotateY: 0, duration: 0.6, ease: 'power3.out' });
    });
  });
}

/* ---------- Cursor glow ---------- */
function initCursorGlow() {
  if (isTouch || prefersReduced) return;
  const glow = document.querySelector<HTMLElement>('.cursor-glow');
  if (!glow) return;
  window.addEventListener('mousemove', (e) => {
    glow.style.opacity = '1';
    gsap.to(glow, { x: e.clientX, y: e.clientY, duration: 0.55, ease: 'power2.out' });
  });
  document.addEventListener('mouseleave', () => {
    glow.style.opacity = '0';
  });
}

/* ---------- Copy-to-clipboard ---------- */
function initCopy() {
  document.querySelectorAll<HTMLElement>('[data-copy]').forEach((el) => {
    el.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(el.dataset.copy || '');
        el.classList.add('copied');
        const icon = el.querySelector('.copy-field__icon');
        const prev = icon?.textContent;
        if (icon) icon.textContent = 'copied';
        else if (el.classList.contains('copy-mini')) el.textContent = 'copied';
        setTimeout(() => {
          el.classList.remove('copied');
          if (icon && prev) icon.textContent = prev;
          else if (el.classList.contains('copy-mini')) el.textContent = 'copy';
        }, 1500);
      } catch {
        /* clipboard unavailable */
      }
    });
  });
}

/* ---------- MCP orbit chips ---------- */
// The actual 15 tools the MCP server exposes (verified via tools/list) — not library-only APIs.
const MCP_TOOLS = [
  'remember', 'recall', 'revert', 'route', 'observe',
  'reopened', 'resolve_reopened', 'consolidate', 'sleep', 'consolidate_clusters',
  'contradictions', 'check_conflict', 'value_by_cohort', 'credit', 'forget',
];
function initOrbit() {
  const orbit = document.getElementById('orbit');
  if (!orbit) return;
  const rings = [
    { r: 0.23, count: 5, dur: 26 },
    { r: 0.36, count: 5, dur: -34 },
    { r: 0.49, count: 5, dur: 44 },
  ];
  let idx = 0;
  rings.forEach((ring) => {
    const layer = document.createElement('div');
    layer.style.position = 'absolute';
    layer.style.inset = '0';
    orbit.appendChild(layer);
    for (let i = 0; i < ring.count; i++) {
      const chip = document.createElement('div');
      chip.className = 'orbit__chip';
      chip.textContent = MCP_TOOLS[idx++ % MCP_TOOLS.length];
      // stagger each ring's start angle so chips never align radially (no 3-o'clock pile-up)
      const angle = (i / ring.count) * Math.PI * 2 + rings.indexOf(ring) * 0.45;
      const x = 50 + Math.cos(angle) * ring.r * 100;
      const y = 50 + Math.sin(angle) * ring.r * 100;
      chip.style.left = `${x}%`;
      chip.style.top = `${y}%`;
      layer.appendChild(chip);
    }
    if (!prefersReduced) {
      gsap.to(layer, { rotate: ring.dur > 0 ? 360 : -360, duration: Math.abs(ring.dur), ease: 'none', repeat: -1 });
      // Counter-rotate chips so text stays upright.
      gsap.to(layer.querySelectorAll('.orbit__chip'), { rotate: ring.dur > 0 ? -360 : 360, duration: Math.abs(ring.dur), ease: 'none', repeat: -1 });
    }
  });
}

export function initInteractions() {
  initReveals((el) => {
    el.querySelectorAll<HTMLElement>('.count').forEach(countUp);
    if (el.classList.contains('count')) countUp(el as HTMLElement);
    if (el.id === 'bench') drawBench(el as HTMLElement);
    if (el.id === 'terminal') {
      const body = document.getElementById('term-body');
      if (body && !body.dataset.done) {
        body.dataset.done = '1';
        typeTerminal(body);
      }
    }
  });
  // Count strip lives in a non-.reveal strip; observe directly.
  const strip = document.getElementById('stats');
  if (strip) {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          strip.querySelectorAll<HTMLElement>('.count').forEach(countUp);
          io.disconnect();
        }
      }
    }, { threshold: 0.4 });
    io.observe(strip);
  }
  initMagnetic();
  initCards();
  initCursorGlow();
  initCopy();
  initOrbit();
}
