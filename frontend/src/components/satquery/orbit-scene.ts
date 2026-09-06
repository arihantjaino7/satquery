/* ── the hero scene ───────────────────────────────────────────────────
   The reference hero drives its centrepiece with three.js: a procedurally
   grown moss root, ~2600 lines of geometry and four custom materials. That
   is the wrong shape of cost for a prototype, so the orbit is drawn on a 2D
   context instead — one path per frame plus two point clouds, no shader
   compile, no second GL context, and it starts painting on the first frame.

   Everything static is built once at mount; the loop only advances two
   angles and re-fills. */

const STAR_COUNT = 380;
const CITY_COUNT = 260;

interface Star {
  x: number;
  y: number;
  r: number;
  a: number;
  /** twinkle phase, so the field doesn't pulse in unison */
  p: number;
  /** parallax depth, 0 = far (still) … 1 = near (rides the pointer) */
  d: number;
}

interface City {
  /** position on the globe in radians: longitude from the sub-view point */
  lon: number;
  lat: number;
  a: number;
}

/** xorshift so the field is identical across reloads — a hero that
 * re-scatters its stars on every refresh reads as noise, not as a sky. */
function makeRng(seed: number) {
  let s = seed >>> 0;
  return () => {
    s ^= s << 13;
    s ^= s >>> 17;
    s ^= s << 5;
    return ((s >>> 0) % 100000) / 100000;
  };
}

function buildStars(): Star[] {
  const rng = makeRng(0x5a7c19);
  return Array.from({ length: STAR_COUNT }, () => {
    const bright = rng();
    return {
      x: rng(),
      // biased upward: the lower half of the frame is planet and airglow
      y: rng() * rng(),
      r: 0.35 + bright * bright * 1.15,
      a: 0.18 + bright * 0.62,
      p: rng() * Math.PI * 2,
      d: rng(),
    };
  });
}

/** City lights clustered into a handful of coastal-looking blobs rather than
 * scattered evenly — an even sprinkle reads as sensor noise, not as land. */
function buildCities(): City[] {
  const rng = makeRng(0x1f3b7d);
  const clusters = Array.from({ length: 9 }, () => ({
    lon: (rng() - 0.5) * 3.4,
    lat: rng() * 0.9,
    spread: 0.1 + rng() * 0.26,
  }));
  return Array.from({ length: CITY_COUNT }, () => {
    const c = clusters[Math.floor(rng() * clusters.length)];
    return {
      lon: c.lon + (rng() - 0.5) * c.spread * 3,
      lat: c.lat + (rng() - 0.5) * c.spread,
      a: 0.25 + rng() * rng() * 0.75,
    };
  });
}

export function mountScene(canvas: HTMLCanvasElement, host: HTMLElement) {
  const ctx = canvas.getContext("2d", { alpha: true });
  if (!ctx) return () => {};

  const stars = buildStars();
  const cities = buildCities();
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  let w = 0;
  let h = 0;
  let frame = 0;
  let t = 0;
  let last = performance.now();
  let visible = true;

  const resize = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const rect = canvas.getBoundingClientRect();
    w = rect.width;
    h = rect.height;
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  };

  const draw = () => {
    if (!w || !h) return;
    // the pointer offset the hero publishes for the CSS layers, reused here
    // so the sky drifts with the panels instead of against them
    const cs = getComputedStyle(host);
    const px = parseFloat(cs.getPropertyValue("--px")) || 0;
    const py = parseFloat(cs.getPropertyValue("--py")) || 0;

    ctx.clearRect(0, 0, w, h);

    /* The stage is 16:9 on the wide layout and nearly 2:1 the other way on
       the narrow one, where the same framing would leave a dead black band
       between the copy and the limb. `sky` is how much of the frame is sky:
       the planet drops and the stars spread to fill it. */
    const tall = h / w > 1;
    const sky = tall ? 0.66 : 0.44;

    // ── stars ────────────────────────────────────────────────────────
    for (const s of stars) {
      const tw = reduced ? 1 : 0.72 + 0.28 * Math.sin(t * 1.7 + s.p);
      const x = s.x * w - px * (4 + s.d * 14);
      const y = (tall ? s.y * 0.55 + s.y * s.y * 0.45 : s.y) * h * (sky / 0.44) * 0.8 - py * (2 + s.d * 8);
      ctx.fillStyle = `rgba(226, 234, 255, ${s.a * tw})`;
      ctx.fillRect(x, y, s.r, s.r);
    }

    // ── the planet ───────────────────────────────────────────────────
    // A limb across the lower frame, seen from low orbit: the disc is far
    // wider than the stage, so only the top of the arc is in shot.
    const r = w * 1.05;
    const cx = w * 0.5 - px * 3;
    const cy = h * sky + r - py * 2;

    ctx.save();
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.clip();

    const body = ctx.createLinearGradient(0, cy - r, 0, cy - r + h);
    body.addColorStop(0, "#22315e");
    body.addColorStop(0.28, "#131d3c");
    body.addColorStop(1, "#05070f");
    ctx.fillStyle = body;
    ctx.fillRect(0, cy - r, w, h * 2);

    // the sun sits off the upper left, so the limb is brightest there and
    // falls into the terminator on the right
    const sun = ctx.createRadialGradient(w * 0.18, cy - r * 1.01, 0, w * 0.18, cy - r * 1.01, w * 0.95);
    sun.addColorStop(0, "rgba(150, 180, 255, 0.34)");
    sun.addColorStop(0.45, "rgba(110, 140, 220, 0.1)");
    sun.addColorStop(1, "rgba(110, 140, 220, 0)");
    ctx.fillStyle = sun;
    ctx.fillRect(0, cy - r, w, h * 2);

    // city lights, riding the rotation
    const spin = t * 0.012;
    for (const c of cities) {
      const lon = c.lon + spin;
      const cosLon = Math.cos(lon);
      if (cosLon <= 0.02) continue; // on the far side
      const x = cx + Math.sin(lon) * r * 0.98 * Math.cos(c.lat);
      const y = cy - r * 0.985 * Math.cos(c.lat * 0.9) * cosLon;
      // dimmer as it turns away from the viewer, warmer near the terminator
      const fall = cosLon * cosLon;
      ctx.fillStyle = `rgba(255, 214, 164, ${c.a * fall * 0.85})`;
      ctx.fillRect(x, y, 1.15, 1.15);
    }
    ctx.restore();

    // ── atmosphere ───────────────────────────────────────────────────
    // One ring gradient rather than a stack of stroked arcs: the falloff is
    // the whole effect and a gradient gives it for a single fill.
    const air = ctx.createRadialGradient(cx, cy, r * 0.975, cx, cy, r * 1.045);
    air.addColorStop(0, "rgba(120, 160, 255, 0)");
    air.addColorStop(0.42, "rgba(138, 176, 255, 0.5)");
    air.addColorStop(0.62, "rgba(120, 160, 255, 0.16)");
    air.addColorStop(1, "rgba(120, 160, 255, 0)");
    ctx.beginPath();
    ctx.arc(cx, cy, r * 1.045, 0, Math.PI * 2);
    ctx.fillStyle = air;
    ctx.fill();

    // ── the satellite ────────────────────────────────────────────────
    // It runs an ellipse above the limb and paints a downlink cone at the
    // ground track — the one thing in the frame that is unmistakably ours.
    const ox = w * 0.5;
    const oy = h * (sky + 0.08);
    const orbitA = w * 0.46;
    const orbitB = Math.min(h * 0.3, w * 0.19);
    const ang = -Math.PI * 0.86 + t * 0.055;

    ctx.strokeStyle = "rgba(168, 180, 240, 0.13)";
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 7]);
    ctx.beginPath();
    ctx.ellipse(ox - px * 8, oy - py * 5, orbitA, orbitB, 0, Math.PI, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    const sx = ox - px * 8 + Math.cos(ang) * orbitA;
    const sy = oy - py * 5 + Math.sin(ang) * orbitB;

    // downlink cone: a soft wedge from the craft to its ground track
    const beamW = w * 0.055;
    const reach = Math.min(h * 0.34, w * 0.22);
    const beam = ctx.createLinearGradient(sx, sy, sx, sy + reach);
    beam.addColorStop(0, "rgba(168, 190, 255, 0.16)");
    beam.addColorStop(1, "rgba(168, 190, 255, 0)");
    ctx.beginPath();
    ctx.moveTo(sx, sy);
    ctx.lineTo(sx - beamW, sy + reach);
    ctx.lineTo(sx + beamW, sy + reach);
    ctx.closePath();
    ctx.fillStyle = beam;
    ctx.fill();

    // the craft: a body and two panels, at the scale of a bright star
    const u = Math.max(w / 1600, 0.5);
    ctx.save();
    ctx.translate(sx, sy);
    ctx.fillStyle = "rgba(226, 234, 255, 0.92)";
    ctx.fillRect(-3 * u, -3 * u, 6 * u, 6 * u);
    ctx.fillStyle = "rgba(168, 180, 240, 0.7)";
    ctx.fillRect(-13 * u, -1.6 * u, 8 * u, 3.2 * u);
    ctx.fillRect(5 * u, -1.6 * u, 8 * u, 3.2 * u);
    ctx.restore();
  };

  const loop = (now: number) => {
    frame = requestAnimationFrame(loop);
    if (!visible) return;
    const dt = Math.min(now - last, 64) / 1000;
    last = now;
    t += dt;
    draw();
  };

  const observer = new ResizeObserver(() => {
    resize();
    draw();
  });
  observer.observe(canvas);

  // an off-screen hero should not be burning a frame budget the console
  // section below it wants
  const io = new IntersectionObserver(
    (entries) => {
      visible = entries[0]?.isIntersecting ?? true;
      last = performance.now();
    },
    { threshold: 0 },
  );
  io.observe(canvas);

  resize();
  if (reduced) draw();
  else frame = requestAnimationFrame(loop);

  return () => {
    cancelAnimationFrame(frame);
    observer.disconnect();
    io.disconnect();
  };
}

/* ── data chips ───────────────────────────────────────────────────────
   The reference cards carry photographs. This one has no photography to
   carry, so each card's window gets a synthetic scene chip: value-noise
   terrain run through a false-colour ramp for the optical card and a
   speckle ramp for the SAR one. Painted once, at mount. */

function hash2(x: number, y: number) {
  const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453;
  return n - Math.floor(n);
}

function vnoise(x: number, y: number) {
  const ix = Math.floor(x);
  const iy = Math.floor(y);
  const fx = x - ix;
  const fy = y - iy;
  const ux = fx * fx * (3 - 2 * fx);
  const uy = fy * fy * (3 - 2 * fy);
  const a = hash2(ix, iy);
  const b = hash2(ix + 1, iy);
  const c = hash2(ix, iy + 1);
  const d = hash2(ix + 1, iy + 1);
  return a + (b - a) * ux + (c - a) * uy + (a - b - c + d) * ux * uy;
}

function fbm(x: number, y: number, octaves = 4) {
  let v = 0;
  let amp = 0.5;
  let f = 1;
  for (let i = 0; i < octaves; i++) {
    v += vnoise(x * f, y * f) * amp;
    f *= 2.02;
    amp *= 0.5;
  }
  return v;
}

export type ChipKind = "optical" | "sar";

/** Paint a synthetic scene chip into `canvas` at its backing-store size. */
export function paintChip(canvas: HTMLCanvasElement, kind: ChipKind) {
  const W = 220;
  const H = 170;
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");
  if (!ctx) return;

  const img = ctx.createImageData(W, H);
  const px = img.data;
  const seed = kind === "optical" ? 3.1 : 11.7;

  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const nx = (x / W) * 5 + seed;
      const ny = (y / H) * 4 + seed;
      const land = fbm(nx, ny);
      // one meandering channel through the tile, the feature the eye reads
      const river = Math.abs(land - 0.46);
      const i = (y * W + x) * 4;

      let r: number;
      let g: number;
      let b: number;
      if (kind === "optical") {
        // false colour: NIR in the red channel, so vegetation burns red and
        // water goes near-black — the way an agency preview actually looks
        const veg = Math.pow(Math.max(land - 0.4, 0) * 2.2, 0.8);
        const bare = Math.max(0.62 - land, 0) * 1.6;
        r = 34 + veg * 210 + bare * 90;
        g = 30 + veg * 70 + bare * 80;
        b = 52 + bare * 70 + Math.max(0.44 - land, 0) * 120;
        if (river < 0.018) {
          r = 16;
          g = 28;
          b = 62;
        }
      } else {
        // SAR: multiplicative speckle over a backscatter field, bright
        // double-bounce returns where the structure is
        const speckle = 0.55 + hash2(x * 1.7, y * 2.3) * 0.9;
        const back = Math.pow(land, 1.4) * speckle;
        const v = 22 + back * 235;
        r = v * 0.92;
        g = v * 0.96;
        b = v;
        if (river < 0.02) {
          r = g = b = 10;
        }
      }

      px[i] = Math.min(255, r);
      px[i + 1] = Math.min(255, g);
      px[i + 2] = Math.min(255, b);
      px[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  // graticule + a footprint box, so the chip reads as an instrument frame
  ctx.strokeStyle = "rgba(226, 234, 255, 0.12)";
  ctx.lineWidth = 1;
  for (let i = 1; i < 4; i++) {
    ctx.beginPath();
    ctx.moveTo((W / 4) * i, 0);
    ctx.lineTo((W / 4) * i, H);
    ctx.moveTo(0, (H / 4) * i);
    ctx.lineTo(W, (H / 4) * i);
    ctx.stroke();
  }
  ctx.strokeStyle = kind === "optical" ? "rgba(255, 214, 164, 0.85)" : "rgba(168, 216, 255, 0.85)";
  ctx.lineWidth = 1.5;
  ctx.strokeRect(W * 0.52, H * 0.3, W * 0.28, H * 0.34);
}
