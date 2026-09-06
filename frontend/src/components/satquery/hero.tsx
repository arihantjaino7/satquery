import { useEffect, useRef } from "react";
import { mountScene, paintChip } from "@/components/satquery/orbit-scene";
import "@/components/satquery/orbit.css";

/* ── the orbital hero ─────────────────────────────────────────────────
   Structure, motion and interaction model follow the Sylva "living green"
   hero: a 1600 × 880 reference stage, clip-path entrance wipes staggered by
   --d, a pointer parallax published once a frame as --px/--py, and a dock
   whose pills magnify on a spring as the pointer nears them. What changed is
   the world — orbit instead of moss — and the centrepiece, which is a 2D
   canvas here rather than a procedural three.js scene. */

const REDUCED = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** layers that ride the pointer; each declares its own --pd / --pr */
const PARALLAX_SEL =
  ".o-dock,.o-headline,.o-lede,.o-pill,.o-scan-wrap,.o-stat--a,.o-stat--b,.o-card--brief,.o-card--note,.o-scroll";

function clamp01(x: number) {
  return x < 0 ? 0 : x > 1 ? 1 : x;
}

interface DockState {
  el: HTMLElement;
  w: number;
  h: number;
  v: number;
  vel: number;
  target: number;
}

/** Pointer parallax + the dock's magnification spring + the specular rim,
 * all on one rAF. Returns a cleanup. */
function startMotion(hero: HTMLElement, dock: HTMLElement) {
  if (REDUCED()) return () => {};

  const layers = Array.from(hero.querySelectorAll<HTMLElement>(PARALLAX_SEL));
  for (const el of layers) el.classList.add("o-par");

  const items: DockState[] = Array.from(dock.querySelectorAll<HTMLElement>("[data-dock]")).map((el) => ({
    el,
    w: 0,
    h: 0,
    v: 0,
    vel: 0,
    target: 0,
  }));

  let aimX = 0;
  let aimY = 0;
  let aimSeen = false;
  let aimMoved = false;
  let dockLive = false;
  let dockDirty = true;
  let unit = 1;

  const pointer = { x: 0, y: 0 };
  const smooth = { x: 0, y: 0 };
  let lastX: number | null = null;
  let lastY: number | null = null;
  let spec = { angle: 2.4, bright: 0, tAngle: 2.4, tBright: 0 };

  const measure = () => {
    unit = hero.getBoundingClientRect().width / (window.matchMedia("(max-width: 900px)").matches ? 760 : 1600);
    for (const st of items) {
      st.el.style.width = st.el.style.height = st.el.style.transform = "";
      st.el.dataset.near = "false";
      st.v = st.vel = st.target = 0;
    }
    for (const st of items) {
      const r = st.el.getBoundingClientRect();
      st.w = r.width;
      st.h = r.height;
    }
    dockDirty = true;
  };

  const rest = () => {
    dockLive = false;
    dockDirty = true;
    for (const st of items) {
      st.target = 0;
      st.el.dataset.near = "false";
    }
  };

  const drawDock = (dt: number) => {
    /* Targets are only recomputed when the pointer actually MOVES. Re-deriving
       them every frame from a stale position oscillates: the capsule is
       centred, so a growing pill shifts the bar sideways, which slides a
       different pill under a stationary cursor, which grows instead. */
    if (aimSeen && aimMoved) {
      const rr = dock.getBoundingClientRect();
      // the catch box reaches well below the bar, because that is where the
      // pills grow to and the pointer has to be able to follow them
      if (aimX > rr.left - 48 && aimX < rr.right + 48 && aimY > rr.top - 44 && aimY < rr.bottom + 104) {
        for (const st of items) {
          const r = st.el.getBoundingClientRect();
          const prox = clamp01(1 - Math.abs(aimX - (r.left + r.width * 0.5)) / (128 * unit));
          st.target = prox * prox * (3 - 2 * prox);
          st.el.dataset.near = st.target > 0.08 ? "true" : "false";
        }
        dockLive = true;
        dockDirty = true;
      } else if (dockLive) rest();
    }

    if (!dockDirty) return;
    let moving = false;
    for (const st of items) {
      st.vel += (st.target - st.v) * 190 * dt;
      st.vel *= Math.exp(-23 * dt);
      st.v += st.vel * dt;
      if (Math.abs(st.target - st.v) < 0.001 && Math.abs(st.vel) < 0.004) {
        st.v = st.target;
        st.vel = 0;
      } else moving = true;

      const v = Math.min(Math.max(st.v, 0), 1.08);
      const mark = st.el.classList.contains("o-dock-mark");
      const ew = mark ? 14 * unit : Math.min(18 * unit, st.w * 0.24);
      const eh = mark ? 14 * unit : 16 * unit;
      st.el.style.width = `${(st.w + ew * v).toFixed(2)}px`;
      st.el.style.height = `${(st.h + eh * v).toFixed(2)}px`;
      st.el.style.transform = `translateY(${(v * 3.5 * unit).toFixed(2)}px)`;
    }
    if (!moving) dockDirty = false;
  };

  /* The rim highlight points at the pointer and dims with distance — the
     reason the capsule reads as lit glass and not a flat translucent box. */
  const drawSpec = (dt: number) => {
    if (aimSeen && aimMoved) {
      const r = dock.getBoundingClientRect();
      const cx = r.left + r.width * 0.5;
      const cy = r.top + r.height * 0.5;
      const dx = Math.max(r.left - aimX, 0, aimX - r.right);
      const dy = Math.max(r.top - aimY, 0, aimY - r.bottom);
      const d = Math.hypot(dx, dy);
      spec.tAngle = Math.atan2(aimY - cy, aimX - cx) + Math.PI;
      spec.tBright = clamp01(1 - d / 420);
    }
    const k = 1 - Math.exp(-9 * dt);
    // shortest way round, so the highlight never sweeps the long way
    let delta = spec.tAngle - spec.angle;
    while (delta > Math.PI) delta -= Math.PI * 2;
    while (delta < -Math.PI) delta += Math.PI * 2;
    spec.angle += delta * k;
    spec.bright += (spec.tBright - spec.bright) * k;
    dock.style.setProperty("--spec-angle", `${spec.angle.toFixed(3)}rad`);
    dock.style.setProperty("--spec-bright", spec.bright.toFixed(3));
  };

  let last = 0;
  let frame = 0;
  const loop = (now: number) => {
    frame = requestAnimationFrame(loop);
    const dt = last ? Math.min((now - last) / 1000, 0.05) : 0.016;
    last = now;

    drawDock(dt);
    drawSpec(dt);
    aimMoved = false;

    smooth.x += (pointer.x - smooth.x) * 0.055;
    smooth.y += (pointer.y - smooth.y) * 0.055;
    /* three decimals is finer than a pixel of travel, and rounding lets the
       writes stop entirely once the pointer settles — no style invalidation
       on an idle page */
    const nx = Math.round(smooth.x * 1000) / 1000;
    const ny = Math.round(smooth.y * 1000) / 1000;
    if (nx !== lastX || ny !== lastY) {
      lastX = nx;
      lastY = ny;
      hero.style.setProperty("--px", String(nx));
      hero.style.setProperty("--py", String(ny));
    }
  };

  const onMove = (e: PointerEvent) => {
    if (e.pointerType === "touch") return;
    const r = hero.getBoundingClientRect();
    pointer.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    pointer.y = ((e.clientY - r.top) / r.height) * 2 - 1;
    aimX = e.clientX;
    aimY = e.clientY;
    aimSeen = true;
    aimMoved = true;
  };
  const onLeave = () => {
    pointer.x = pointer.y = 0;
    spec.tBright = 0;
    rest();
  };

  window.addEventListener("pointermove", onMove, { passive: true });
  window.addEventListener("pointerleave", onLeave);
  window.addEventListener("resize", measure);

  measure();
  frame = requestAnimationFrame(loop);

  return () => {
    cancelAnimationFrame(frame);
    window.removeEventListener("pointermove", onMove);
    window.removeEventListener("pointerleave", onLeave);
    window.removeEventListener("resize", measure);
    for (const el of layers) el.classList.remove("o-par");
  };
}

function scrollToConsole() {
  document.getElementById("query")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

/** the knob glyph both cards carry: an aperture, opened */
function KnobGlyph() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="8.4" />
      <path d="M12 3.6v5M12 15.4v5M3.6 12h5M15.4 12h5" />
      <circle cx="12" cy="12" r="2.1" />
    </svg>
  );
}

export function Hero() {
  const heroRef = useRef<HTMLElement>(null);
  const dockRef = useRef<HTMLElement>(null);
  const sceneRef = useRef<HTMLCanvasElement>(null);
  const opticalRef = useRef<HTMLCanvasElement>(null);
  const sarRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const hero = heroRef.current;
    const dock = dockRef.current;
    const scene = sceneRef.current;
    if (!hero || !dock || !scene) return;

    if (opticalRef.current) paintChip(opticalRef.current, "optical");
    if (sarRef.current) paintChip(sarRef.current, "sar");

    const stopScene = mountScene(scene, hero);
    const stopMotion = startMotion(hero, dock);

    // the intro runs one frame after mount so the wipes have a start state,
    // and `intro-done` drops the clips once they have landed
    const raf = requestAnimationFrame(() => hero.classList.add("is-ready"));
    const done = window.setTimeout(() => hero.classList.add("intro-done"), REDUCED() ? 0 : 2900);

    return () => {
      cancelAnimationFrame(raf);
      clearTimeout(done);
      stopScene();
      stopMotion();
      hero.classList.remove("is-ready", "intro-done");
    };
  }, []);

  return (
    <section ref={heroRef} className="orbit-hero dark" id="hero">
      <div className="o-stage" id="stage">
        <canvas ref={sceneRef} className="o-scene" aria-hidden="true" />

        <div className="o-guides o-fade" style={{ "--d": "900ms" } as React.CSSProperties} aria-hidden="true">
          <i style={{ left: "calc(405 * var(--u))" }} />
          <i style={{ left: "calc(748 * var(--u))" }} />
          <i style={{ left: "calc(1091 * var(--u))" }} />
        </div>

        <div className="o-ghost o-fade" style={{ "--d": "1150ms" } as React.CSSProperties} aria-hidden="true">
          SATQUERY
        </div>

        <div className="o-dock-wrap">
          <nav ref={dockRef} className="o-dock" data-spec aria-label="Primary">
            <a
              className="o-dock-item o-dock-mark"
              data-dock
              href="#hero"
              style={{ "--d": "120ms" } as React.CSSProperties}
              aria-label="SatQuery — home"
            >
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="9.5" y="9.5" width="5" height="5" rx="1" />
                <path d="M2.5 12h5M16.5 12h5M12 2.5v5M12 16.5v5" />
              </svg>
            </a>
            <button className="o-dock-item is-active" data-dock type="button" style={{ "--d": "180ms" } as React.CSSProperties}>
              <span className="o-glyph" aria-hidden="true">
                <svg viewBox="0 0 16 16">
                  <circle cx="8" cy="8" r="5.6" />
                  <path d="M2.4 8h11.2M8 2.4c1.5 1.6 2.3 3.6 2.3 5.6S9.5 12 8 13.6C6.5 12 5.7 10 5.7 8S6.5 4 8 2.4Z" />
                </svg>
              </span>
              <span>Mission</span>
            </button>
            <button className="o-dock-item" data-dock type="button" style={{ "--d": "230ms" } as React.CSSProperties} onClick={scrollToConsole}>
              <span className="o-glyph" aria-hidden="true">
                <svg viewBox="0 0 16 16">
                  <path d="M2.4 11.6 6 8l2.4 2.4L13.6 5" />
                  <path d="M10.4 5h3.2v3.2" />
                </svg>
              </span>
              <span>Pipeline</span>
            </button>
            <button className="o-dock-item" data-dock type="button" style={{ "--d": "280ms" } as React.CSSProperties} onClick={scrollToConsole}>
              <span className="o-glyph" aria-hidden="true">
                <svg viewBox="0 0 16 16">
                  <path d="M4 2.6h5.3L12 5.3v8.1H4z" />
                  <path d="M9.2 2.6v2.7h2.8M6 8.6h4M6 11h2.8" />
                </svg>
              </span>
              <span>Trace</span>
            </button>
            <button
              className="o-dock-item o-dock-item--enter"
              data-dock
              type="button"
              style={{ "--d": "330ms" } as React.CSSProperties}
              onClick={scrollToConsole}
            >
              <span className="o-glyph" aria-hidden="true">
                <svg viewBox="0 0 16 16">
                  <path d="M6.6 2.5h5.1a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H6.6" />
                  <path d="M2.6 8h6.6M7 5.6 9.4 8 7 10.4" />
                </svg>
              </span>
              <span>Upload</span>
            </button>
          </nav>
        </div>

        <h1 className="o-headline" style={{ "--pd": 18, "--pr": 1.2 } as React.CSSProperties}>
          <span>
            <i style={{ "--d": "260ms" } as React.CSSProperties}>Point a question</i>
          </span>
          <span>
            <i style={{ "--d": "360ms" } as React.CSSProperties}>
              at the <em>planet.</em>
            </i>
          </span>
        </h1>

        <p className="o-lede o-mask" style={{ "--d": "480ms", "--pd": 14, "--pr": 1 } as React.CSSProperties}>
          Raw satellite imagery in, plain English out — segmentation, change detection and captioning behind one
          question, with every step left on the record.
        </p>

        <button
          type="button"
          onClick={scrollToConsole}
          className="o-pill o-mask"
          style={{ "--d": "600ms", "--pd": 15, "--pr": 1.4 } as React.CSSProperties}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 16V4M8 8l4-4 4 4M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" />
          </svg>
          Upload imagery
        </button>

        <span className="o-scan-wrap" style={{ "--pd": 20 } as React.CSSProperties}>
          <button
            type="button"
            onClick={scrollToConsole}
            className="o-scan o-mask-circle"
            style={{ "--d": "900ms" } as React.CSSProperties}
            aria-label="Run a sample scene"
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="7" />
              <path d="M12 1.5v4M12 18.5v4M1.5 12h4M18.5 12h4" />
              <circle cx="12" cy="12" r="1.6" />
            </svg>
          </button>
          <span className="o-scan-ring" aria-hidden="true" />
        </span>

        <dl className="o-stat o-stat--a o-mask" style={{ "--d": "700ms", "--pd": 12 } as React.CSSProperties}>
          <span className="o-mark" aria-hidden="true">
            <svg viewBox="0 0 30 30" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
              <circle cx="15" cy="15" r="10.5" strokeDasharray="0.6 3.6" />
              <circle cx="15" cy="15" r="5.6" strokeDasharray="0.6 3.2" />
              <circle cx="15" cy="15" r="1.1" fill="currentColor" stroke="none" />
            </svg>
          </span>
          <div>
            <dt>Sensors fused</dt>
            <dd>Sentinel-1 + 2</dd>
          </div>
        </dl>

        <dl className="o-stat o-stat--b o-mask" style={{ "--d": "770ms", "--pd": 13 } as React.CSSProperties}>
          <span className="o-mark" aria-hidden="true">
            <svg viewBox="0 0 30 30" fill="none" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round">
              <path d="M15 3.5v5M15 21.5v5M3.5 15h5M21.5 15h5" />
              <path d="m6.9 6.9 3.5 3.5M19.6 19.6l3.5 3.5M23.1 6.9l-3.5 3.5M10.4 19.6l-3.5 3.5" />
              <circle cx="15" cy="15" r="3.6" />
            </svg>
          </span>
          <div>
            <dt>Every answer</dt>
            <dd>Traced end to end</dd>
          </div>
        </dl>

        <article className="o-card o-card--brief o-mask" style={{ "--d": "760ms", "--pd": 10, "--pr": 2.2 } as React.CSSProperties}>
          <figure>
            <canvas ref={opticalRef} className="o-chip" aria-label="False-colour optical scene chip" />
          </figure>
          <p className="o-label">Mission brief</p>
          <h2>Grounded, never guessed.</h2>
          <button className="o-knob" type="button" onClick={scrollToConsole} aria-label="Read the mission brief">
            <KnobGlyph />
          </button>
        </article>

        <article className="o-card o-card--note o-mask" style={{ "--d": "880ms", "--pd": 22, "--pr": 2.4 } as React.CSSProperties}>
          <p className="o-label">Scene 07 · SAR</p>
          <h2>After the flood</h2>
          <figure>
            <canvas ref={sarRef} className="o-chip" aria-label="Synthetic-aperture radar scene chip" />
          </figure>
          <button className="o-knob" type="button" onClick={scrollToConsole} aria-label="Open scene 07">
            <KnobGlyph />
          </button>
        </article>

        <button
          type="button"
          onClick={scrollToConsole}
          className="o-scroll o-mask"
          style={{ "--d": "1040ms", "--pd": 9 } as React.CSSProperties}
        >
          Upload
          <span className="o-track" />
        </button>
      </div>
    </section>
  );
}
