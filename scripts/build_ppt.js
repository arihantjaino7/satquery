/*  SatQuery AI - SIH 2026 Idea Submission deck
 *  Format deliberately mirrors the official SIH template (ZyraNav reference):
 *  white ground, blue section headings, blue footer bar, Times New Roman body,
 *  team-name oval top-left. No new design language is introduced.
 *
 *  Rebuild:  node scripts/build_ppt.js
 */
const pptxgen = require("pptxgenjs");

// ---- fill these two in, then rebuild -------------------------------------
const TEAM_NAME = "Oryn";
const TEAM_ID   = "Not Assigned Yet";
const LOGO_ICON = __dirname + "/sih_icon.png";   // cropped from the reference deck
// --------------------------------------------------------------------------

const PS_ID    = "26167";
const PS_TITLE = "SatQuery AI: An Interactive Vision-Language Assistant for Multimodal " +
                 "Remote Sensing Image Analysis through Text Queries";

const BAR   = "1F6FC5";   // footer bar / template blue
const HEAD  = "1F4E79";   // section heading blue
const INK   = "000000";
const RED   = "C00000";   // dashed dividers, as in the reference
const SERIF = "Times New Roman";
const SANS  = "Calibri";

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";            // 13.3 x 7.5 - set BEFORE adding slides
pres.author = TEAM_NAME;
pres.title  = "SatQuery AI - SIH 2026 Idea Submission";

const W = 13.33, H = 7.5;
const BODY_Y = 0.88, BODY_B = 6.88;

/* helpers ---------------------------------------------------------------- */

// parts = [[text, bold?], ...]  -> one bulleted paragraph
function bullet(parts, opt = {}) {
  const runs = parts.map((p, i) => ({
    text: p[0],
    options: Object.assign({ bold: !!p[1] }, i === 0 ? { bullet: true } : {},
                           i === parts.length - 1 ? { breakLine: true } : {}),
  }));
  return runs;
}
function bullets(list, opt = {}) {
  return list.flatMap((parts) => bullet(parts));
}
function textBox(slide, runs, o) {
  slide.addText(runs, Object.assign({
    isTextBox: true, fontFace: SERIF, fontSize: 11.5, color: INK,
    margin: 0, valign: "top", paraSpaceAfter: 4, lineSpacing: 15,
  }, o));
}
function heading(slide, txt, x, y, w, o = {}) {
  slide.addText(txt, Object.assign({
    isTextBox: true, x, y, w, h: 0.28, margin: 0,
    fontFace: SERIF, fontSize: 13.5, bold: true, color: HEAD, valign: "top",
  }, o));
}
// standard header + blue footer bar
function chrome(slide, title, pageNo, opts = {}) {
  slide.background = { color: "FFFFFF" };
  // team-name oval, top-left
  slide.addShape(pres.ShapeType.ellipse, {
    x: 0.16, y: 0.08, w: 1.62, h: 0.52,
    fill: { color: "FFFFFF" }, line: { color: BAR, width: 1.25 },
  });
  slide.addText(TEAM_NAME, {
    isTextBox: true, x: 0.16, y: 0.08, w: 1.62, h: 0.52, margin: 0,
    fontFace: SERIF, fontSize: 11, color: INK, align: "center", valign: "middle",
  });
  // slide title
  slide.addText(title, {
    isTextBox: true, x: 1.95, y: 0.05, w: 9.15, h: 0.6, margin: 0,
    fontFace: SERIF, fontSize: opts.titleSize || 22, bold: true,
    italic: !!opts.italic, color: INK, align: "center", valign: "middle",
  });
  // SIH logo icon (cropped from the reference deck) + our own "2026" text —
  // the reference icon graphic itself carries no year, so it's reused as-is.
  slide.addImage({ path: LOGO_ICON, x: 11.28, y: 0.09, w: 0.56, h: 0.5 });
  slide.addText([
    { text: "SMART INDIA", options: { breakLine: true } },
    { text: "HACKATHON" },
  ], {
    isTextBox: true, x: 11.9, y: 0.1, w: 1.3, h: 0.32, margin: 0,
    fontFace: SANS, fontSize: 8, bold: true, color: "44546A",
    align: "left", valign: "top", lineSpacing: 9,
  });
  slide.addText("2026", {
    isTextBox: true, x: 11.9, y: 0.4, w: 1.3, h: 0.18, margin: 0,
    fontFace: SANS, fontSize: 8, bold: true, color: "44546A",
    align: "left", valign: "top",
  });
  // rule under header
  slide.addShape(pres.ShapeType.line, {
    x: 0.1, y: 0.72, w: W - 0.2, h: 0, line: { color: BAR, width: 1 },
  });
  // blue footer bar
  slide.addShape(pres.ShapeType.rect, {
    x: 0, y: BODY_B + 0.04, w: W, h: H - BODY_B - 0.04, fill: { color: BAR },
  });
  slide.addText(String(pageNo), {
    isTextBox: true, x: W - 1.0, y: BODY_B + 0.04, w: 0.7, h: 0.5, margin: 0,
    fontFace: SERIF, fontSize: 12, bold: true, color: "FFFFFF",
    align: "right", valign: "middle",
  });
}
function vrule(slide, x, y1, y2, dash) {
  slide.addShape(pres.ShapeType.line, {
    x, y: y1, w: 0, h: y2 - y1,
    line: Object.assign({ color: dash ? RED : BAR, width: 1 },
                        dash ? { dashType: "dash" } : {}),
  });
}
function hrule(slide, x1, x2, y, dash) {
  slide.addShape(pres.ShapeType.line, {
    x: x1, y, w: x2 - x1, h: 0,
    line: Object.assign({ color: dash ? RED : BAR, width: 1 },
                        dash ? { dashType: "dash" } : {}),
  });
}
// flow-chart node
function node(slide, txt, x, y, w, h, fill, o = {}) {
  slide.addShape(pres.ShapeType.roundRect, {
    x, y, w, h, rectRadius: 0.04,
    fill: { color: fill }, line: { color: "7F7F7F", width: 0.75 },
  });
  slide.addText(txt, {
    isTextBox: true, x, y, w, h, margin: 0.02,
    fontFace: SANS, fontSize: o.fs || 9, bold: !!o.bold, color: INK,
    align: "center", valign: "middle",
  });
}
function arrowDown(slide, x, y, h) {
  slide.addShape(pres.ShapeType.line, {
    x, y, w: 0, h,
    line: { color: "595959", width: 1.25, endArrowType: "triangle" },
  });
}

/* ============================ SLIDE 1 - TITLE ============================ */
{
  const s = pres.addSlide();
  s.background = { color: "FFFFFF" };
  s.addText("SMART INDIA HACKATHON 2026", {
    isTextBox: true, x: 0.6, y: 0.25, w: 9.6, h: 0.75, margin: 0,
    fontFace: SERIF, fontSize: 34, bold: true, color: HEAD,
    align: "center", valign: "middle",
  });
  s.addImage({ path: LOGO_ICON, x: 10.55, y: 0.12, w: 1.02, h: 0.9 });
  s.addText([
    { text: "SMART INDIA", options: { breakLine: true } },
    { text: "HACKATHON", options: { breakLine: true } },
    { text: "2026" },
  ], {
    isTextBox: true, x: 11.65, y: 0.18, w: 1.55, h: 0.78, margin: 0,
    fontFace: SANS, fontSize: 12, bold: true, color: "44546A",
    align: "left", valign: "middle", lineSpacing: 13,
  });
  s.addText("TITLE PAGE", {
    isTextBox: true, x: 0.6, y: 1.25, w: 9.6, h: 0.5, margin: 0,
    fontFace: SERIF, fontSize: 24, bold: true, color: INK,
    align: "center", valign: "middle",
  });

  const rows = [
    ["Problem Statement ID - ", PS_ID],
    ["Problem Statement Title - ", PS_TITLE],
    ["Theme - ", "Space Technology"],
    ["PS Category - ", "Software"],
    ["Team ID - ", TEAM_ID],
    ["Team Name - ", TEAM_NAME],
  ];
  const runs = rows.flatMap(([k, v]) => bullet([[k, true], [v, false]]));
  s.addText(runs, {
    isTextBox: true, x: 0.65, y: 2.0, w: 9.5, h: 4.6, margin: 0,
    fontFace: SERIF, fontSize: 15, color: INK,
    paraSpaceAfter: 16, lineSpacing: 22, valign: "top",
  });
  s.addNotes("PS 26167, ISRO. Software category. Solution name: SatQuery AI.");
}

/* ====================== SLIDE 2 - PROPOSED SOLUTION ====================== */
{
  const s = pres.addSlide();
  chrome(s, "SatQuery AI: An Agentic Vision-Language Assistant for Multimodal " +
            "Remote Sensing Analysis", 2, { titleSize: 15, italic: true });

  const MID = 6.15, ROW = 2.28;
  vrule(s, MID, BODY_Y, ROW - 0.06);
  hrule(s, 0.15, W - 0.15, ROW - 0.02);

  heading(s, "Problem:", 0.2, BODY_Y, 3);
  textBox(s, [
    { text: "Satellite imagery is still read by hand.", options: { bold: true } },
    { text: " An analyst with a Cartosat-2S optical or RISAT SAR scene must open a GIS " +
            "desktop and interpret it manually. Generic AI models cannot help: they ",
      options: {} },
    { text: "hallucinate on nadir imagery, cannot read multi-band GeoTIFF, and are blind " +
            "to SAR backscatter", options: { bold: true } },
    { text: ".", options: {} },
  ], { x: 0.2, y: BODY_Y + 0.3, w: 5.75, h: 1.05, fontSize: 12, lineSpacing: 15 });

  heading(s, "Our Idea:", MID + 0.2, BODY_Y, 3);
  textBox(s, [
    { text: "SatQuery AI", options: { bold: true } },
    { text: " answers plain-English questions about satellite imagery — a single scene, " +
            "a ", options: {} },
    { text: "before-and-after pair", options: { bold: true } },
    { text: ", or a co-registered ", options: {} },
    { text: "optical + SAR pair", options: { bold: true } },
    { text: ". An agentic controller routes each query to remote-sensing-adapted models " +
            "and returns the answer with an ", options: {} },
    { text: "auditable execution trace.", options: { bold: true } },
  ], { x: MID + 0.2, y: BODY_Y + 0.3, w: 6.8, h: 1.05, fontSize: 12, lineSpacing: 15 });

  // ---- row 2: proposed solution | diagram | innovation
  heading(s, "Proposed Solution:", 0.2, ROW + 0.06, 4);
  textBox(s, bullets([
    [["An agentic controller ", true],
     ["interprets the query, classifies the task, validates the images, selects models " +
      "from a typed registry, executes them, fuses text with spatial output and scores " +
      "confidence.", false]],
    [["Remote-sensing adaptation: ", true],
     ["a 12-channel encoder fine-tuned on BigEarthNet consumes 10 optical and 2 SAR bands " +
      "together, so fusion is learned rather than stapled together afterwards.", false]],
    [["Compositional change analysis: ", true],
     ["a siamese detector produces a change mask, statistics are derived from it, and the " +
      "language model verbalises them — every intermediate step is auditable.", false]],
    [["Geospatial correctness first: ", true],
     ["CRS, ground sample distance and sub-pixel grid alignment are verified before any " +
      "cross-modal claim is made.", false]],
  ]), { x: 0.2, y: ROW + 0.36, w: 4.25, h: 4.3, fontSize: 11.5, lineSpacing: 14.5 });

  // ---- centre diagram
  const dx = 4.72, dw = 3.85;
  s.addText("HOW A QUERY IS ANSWERED", {
    isTextBox: true, x: dx, y: ROW + 0.36, w: dw, h: 0.22, margin: 0,
    fontFace: SANS, fontSize: 9, bold: true, color: HEAD, align: "center",
  });
  let y = ROW + 0.66;
  const chip = (t, f, hh) => { node(s, t, dx, y, dw, hh || 0.34, f); };
  chip('"What changed here?"  +  two GeoTIFFs', "FFF2CC");
  y += 0.34; arrowDown(s, dx + dw / 2, y, 0.16); y += 0.16;
  chip("INGEST — CRS, bands, GSD, modality", "DEEBF7");
  y += 0.34; arrowDown(s, dx + dw / 2, y, 0.16); y += 0.16;
  chip("VALIDATE — format, overlap, grid alignment", "DEEBF7");
  y += 0.34; arrowDown(s, dx + dw / 2, y, 0.16); y += 0.16;
  chip("CLASSIFY task  →  SELECT model by rule", "E2EFDA");
  y += 0.34; arrowDown(s, dx + dw / 2, y, 0.16); y += 0.16;
  // registry
  s.addShape(pres.ShapeType.rect, {
    x: dx, y, w: dw, h: 0.92, fill: { color: "FBE5D6" },
    line: { color: "7F7F7F", width: 0.75 },
  });
  s.addText("MODEL REGISTRY", {
    isTextBox: true, x: dx, y: y + 0.03, w: dw, h: 0.18, margin: 0,
    fontFace: SANS, fontSize: 8, bold: true, color: INK, align: "center",
  });
  const rw = (dw - 0.24) / 3;
  ["Optical+SAR\nEncoder", "Change\nDetector", "RS Vision-\nLanguage Model"]
    .forEach((t, i) => node(s, t, dx + 0.06 + i * (rw + 0.06), y + 0.24, rw, 0.62,
                            "FFFFFF", { fs: 7.5 }));
  y += 0.92; arrowDown(s, dx + dw / 2, y, 0.16); y += 0.16;
  chip("FUSE text + spatial  →  CONFIDENCE", "E2EFDA");
  y += 0.34; arrowDown(s, dx + dw / 2, y, 0.16); y += 0.16;
  chip("ANSWER  +  AUDITABLE TRACE", "D9E2F3", 0.38);

  heading(s, "Innovation/Uniqueness:", 8.85, ROW + 0.06, 4.3);
  textBox(s, bullets([
    [["Deterministic model selection.", true],
     [" The language model classifies the task; typed registry rules choose the model. " +
      "The trace is therefore reproducible and auditable, not a chat transcript.", false]],
    [["One fused optical+SAR encoder", true],
     [", trained on co-registered Sentinel-1/2 pairs and proven by a three-way ablation " +
      "where fused beats either sensor alone.", false]],
    [["Co-registration is verified, not assumed.", true],
     [" Sub-pixel grid alignment is checked, not merely footprint overlap.", false]],
    [["Confidence as a named breakdown", true],
     [", including agreement between the language model and the specialist — " +
      "disagreement visibly lowers the score instead of hiding.", false]],
    [["Sensor-correct preprocessing.", true],
     [" SAR is converted to decibels and percentile-clipped, so the model sees terrain " +
      "rather than a black frame.", false]],
  ]), { x: 8.85, y: ROW + 0.36, w: 4.3, h: 4.3, fontSize: 11.5, lineSpacing: 14.5 });
}

/* ====================== SLIDE 3 - TECHNICAL APPROACH ===================== */
{
  const s = pres.addSlide();
  chrome(s, "TECHNICAL APPROACH", 3, { titleSize: 24 });

  const SPLIT = 4.35;
  vrule(s, SPLIT, BODY_Y, BODY_B - 0.02, true);

  s.addText("Technologies Used", {
    isTextBox: true, x: 0.2, y: BODY_Y, w: 4, h: 0.26, margin: 0,
    fontFace: SERIF, fontSize: 13, bold: true, color: INK,
  });
  textBox(s, bullets([
    [["Python 3.11 + FastAPI: ", true],
     ["async backend with native server-sent events, so the execution trace streams to " +
      "the interface as each step completes.", false]],
    [["LangGraph: ", true],
     ["typed state machine with conditional edges. Chosen over a plain agent loop because " +
      "the trace must have inspectable, reproducible transitions.", false]],
    [["rasterio + GDAL: ", true],
     ["reads multi-band GeoTIFF with CRS, affine transform and nodata. Chosen over " +
      "OpenCV/PIL, which silently discard all geospatial metadata.", false]],
    [["pyproj + Shapely: ", true],
     ["projection comparison and footprint intersection for co-registration checks.", false]],
    [["PyTorch: ", true],
     ["12-channel ResNet-50 encoder fine-tuned on BigEarthNet v2.0 for 19-class land cover.",
      false]],
    [["Qwen2.5-VL (RS-adapted) + LoRA: ", true],
     ["3B vision-language model. Chosen over 7B alternatives because domain knowledge sits " +
      "in the encoder, so the model only verbalises — same answer, commodity hardware.", false]],
    [["React + Vite: ", true],
     ["live trace panel driven by the SSE stream.", false]],
    [["Kaggle T4: ", true],
     ["model adaptation runs off the demo machine entirely.", false]],
  ]), { x: 0.2, y: BODY_Y + 0.3, w: 4.0, h: 6.2, fontSize: 10.5, lineSpacing: 13 });

  heading(s, "FLOW CHART", SPLIT + 0.2, BODY_Y, 3, { fontSize: 14 });

  const fx = SPLIT + 0.25, fw = W - fx - 0.25;
  let y = BODY_Y + 0.34;
  const step = (t, f, hh) => { node(s, t, fx, y, fw, hh || 0.36, f, { fs: 10 }); };

  // inputs row
  const iw = (fw - 0.2) / 3;
  ["Text query", "Optical GeoTIFF\n(Cartosat-2S)", "SAR / second-date GeoTIFF\n(RISAT)"]
    .forEach((t, i) => node(s, t, fx + i * (iw + 0.1), y, iw, 0.42, "FFF2CC", { fs: 9 }));
  y += 0.42; arrowDown(s, fx + fw / 2, y, 0.18); y += 0.18;

  step("INGEST  —  checksum, CRS, transform, bands, dtype, nodata, modality from pixels",
       "DEEBF7");
  y += 0.36; arrowDown(s, fx + fw / 2, y, 0.18); y += 0.18;

  step("VALIDATE  —  format, projection match, footprint overlap, GSD ratio, sub-pixel grid " +
       "alignment", "DEEBF7");
  y += 0.36;
  s.addText("fatal  →  reject with a named reason", {
    isTextBox: true, x: fx + fw - 2.6, y: y + 0.01, w: 2.55, h: 0.16, margin: 0,
    fontFace: SANS, fontSize: 7.5, italic: true, color: RED, align: "right",
  });
  arrowDown(s, fx + fw / 2, y, 0.18); y += 0.18;

  const cw = (fw - 0.1) / 2;
  node(s, "CLASSIFY TASK\n(language model, structured output)", fx, y, cw, 0.44,
       "E2EFDA", { fs: 9 });
  node(s, "PLAN — REGISTRY RESOLVER\n(deterministic rules, logged rejections)",
       fx + cw + 0.1, y, cw, 0.44, "E2EFDA", { fs: 9 });
  y += 0.44; arrowDown(s, fx + fw / 2, y, 0.18); y += 0.18;

  // registry band
  s.addShape(pres.ShapeType.rect, {
    x: fx, y, w: fw, h: 0.86, fill: { color: "FBE5D6" },
    line: { color: "7F7F7F", width: 0.75 },
  });
  s.addText("EXECUTE  —  model registry", {
    isTextBox: true, x: fx, y: y + 0.03, w: fw, h: 0.18, margin: 0,
    fontFace: SANS, fontSize: 8.5, bold: true, color: INK, align: "center",
  });
  const mw = (fw - 0.28) / 3;
  [
    "12-channel Optical+SAR Encoder\nfine-tuned on BigEarthNet v2.0",
    "Siamese Change Detector\nmask + change statistics",
    "RS Vision-Language Model\nVQA, captioning, grounding",
  ].forEach((t, i) => node(s, t, fx + 0.07 + i * (mw + 0.07), y + 0.23, mw, 0.56,
                           "FFFFFF", { fs: 7.5 }));
  y += 0.86; arrowDown(s, fx + fw / 2, y, 0.18); y += 0.18;

  step("FUSE text + geometry   →   CONFIDENCE (input quality, task certainty, model " +
       "fitness, cross-model agreement)", "E2EFDA");
  y += 0.36; arrowDown(s, fx + fw / 2, y, 0.18); y += 0.18;

  step("ANSWER  +  BOX/MASK OVERLAY  +  AUDITABLE EXECUTION TRACE", "D9E2F3", 0.4);
  y += 0.4;

  // datasets / links strip
  s.addShape(pres.ShapeType.rect, {
    x: fx, y: y + 0.14, w: fw, h: BODY_B - (y + 0.16),
    fill: { color: "D9E2F3" }, line: { color: "9DC3E6", width: 0.75 },
  });
  s.addText([
    { text: "Training & evaluation data: ", options: { bold: true } },
    { text: "BigEarthNet v2.0 (adaptation)  ·  VRSBench + RSVQA (captioning, grounding, VQA)  " +
            "·  CDVQA (change VQA)", options: { breakLine: true } },
    { text: "GitHub: ", options: { bold: true } },
    { text: "[repository link]        ", options: {} },
    { text: "Demo video: ", options: { bold: true } },
    { text: "[video link]", options: {} },
  ], {
    isTextBox: true, x: fx + 0.12, y: y + 0.2, w: fw - 0.24, h: BODY_B - (y + 0.28),
    margin: 0, fontFace: SERIF, fontSize: 10, color: INK, valign: "middle", lineSpacing: 14,
  });
}

/* =================== SLIDE 4 - FEASIBILITY AND VIABILITY ================= */
{
  const s = pres.addSlide();
  chrome(s, "FEASIBILITY AND VIABILITY", 4, { titleSize: 24 });

  const MID = 6.72, ROW = 3.72;
  vrule(s, MID, BODY_Y, BODY_B - 0.02, true);
  hrule(s, 0.15, MID - 0.02, ROW - 0.06, true);
  hrule(s, MID + 0.02, W - 0.15, ROW - 0.06, true);

  heading(s, "Feasibility", 0.2, BODY_Y, 4);
  textBox(s, bullets([
    [["Every dataset the problem statement names is publicly downloadable", true],
     [" and licence-verified — no gated access, no institutional request.", false]],
    [["BigEarthNet v2.0 provides 549,488 co-registered Sentinel-1/Sentinel-2 pairs", true],
     [" — the only large public archive of aligned optical and radar imagery, so " +
      "cross-modal adaptation needs no proprietary data.", false]],
    [["Adaptation fits free compute.", true],
     [" A 12-channel encoder plus LoRA trains on a free Kaggle T4; no cluster, no " +
      "procurement.", false]],
    [["The geospatial stack installs cleanly.", true],
     [" rasterio ships GDAL-bundled wheels, removing the usual build barrier.", false]],
    [["Hardware-independent by design.", true],
     [" The model layer is swappable, so the same system runs on a 4 GB laptop GPU or " +
      "Apple Silicon.", false]],
  ]), { x: 0.2, y: BODY_Y + 0.3, w: 6.3, h: 2.9, fontSize: 11, lineSpacing: 13.5 });

  heading(s, "Commercial and Operational Viability", MID + 0.2, BODY_Y, 6);
  textBox(s, bullets([
    [["Market validation: ", true],
     ["ISRO/NRSC's Bhoonidhi portal already disseminates open data from 47 satellites. " +
      "The bottleneck is analyst time, not imagery.", false]],
    [["Technical readiness: high.", true],
     [" Every component has a published open-source precedent; the work is integration " +
      "and adaptation, not invention.", false]],
    [["Operational cost: low.", true],
     [" Runs on commodity hardware with open weights and open datasets — no per-seat " +
      "licence, no GPU cluster.", false]],
    [["Sustainable to extend: ", true],
     ["new sensors and models are added as registry configuration, not new code, so the " +
      "system grows with the ISRO archive.", false]],
    [["Deployment path: ", true],
     ["a self-contained web service that can sit inside an institutional network, since " +
      "no imagery has to leave the premises.", false]],
  ]), { x: MID + 0.2, y: BODY_Y + 0.3, w: 6.3, h: 2.9, fontSize: 11, lineSpacing: 13.5 });

  heading(s, "Potential Challenges and Risks", 0.2, ROW, 4);
  textBox(s, bullets([
    [["SAR has extreme dynamic range.", true],
     [" A naive contrast stretch yields a near-black image, and a model will then " +
      "confidently describe an empty scene.", false]],
    [["Real ISRO scenes are not benchmark tiles.", true],
     [" Band order, data type, nodata convention and scene size all differ from public " +
      "512-pixel datasets.", false]],
    [["CDVQA ships question text only", true],
     [" — the change imagery must be sourced separately from the SECOND dataset.", false]],
    [["Generic vision-language models hallucinate", true],
     [" on nadir-view imagery and cannot be trusted unsupervised.", false]],
    [["Co-registration is easy to claim and hard to prove", true],
     [" from footprint overlap alone.", false]],
  ]), { x: 0.2, y: ROW + 0.3, w: 6.3, h: 2.9, fontSize: 11, lineSpacing: 13.5 });

  heading(s, "Strategy for Overcoming Them", MID + 0.2, ROW, 6);
  textBox(s, bullets([
    [["Sensor-correct preprocessing: ", true],
     ["decibel conversion with 2nd/98th percentile clipping and dual-polarisation false " +
      "colour, validated visually against real EOS-04 scenes.", false]],
    [["Scene-scale ingestion: ", true],
     ["windowed reads and tiling, with the tiling recorded in the trace so aggregated " +
      "answers stay explainable.", false]],
    [["Mirror the change dataset early", true],
     [" and cross-check its filenames against the question set before depending on it.", false]],
    [["Ground every claim in a specialist model.", true],
     [" Cross-model disagreement automatically lowers reported confidence.", false]],
    [["Verify sub-pixel grid alignment", true],
     [", not just overlap, before any cross-modal answer is produced.", false]],
  ]), { x: MID + 0.2, y: ROW + 0.3, w: 6.3, h: 2.9, fontSize: 11, lineSpacing: 13.5 });
}

/* ===================== SLIDE 5 - IMPACT AND BENEFITS ===================== */
{
  const s = pres.addSlide();
  chrome(s, "IMPACT AND BENEFITS", 5, { titleSize: 24 });

  const C1 = 0.2, C2 = 4.62, C3 = 9.04, CW = 4.1, BAND = 4.95;
  vrule(s, C2 - 0.2, BODY_Y, BAND - 0.1, true);
  vrule(s, C3 - 0.2, BODY_Y, BAND - 0.1, true);
  hrule(s, 0.15, W - 0.15, BAND, true);

  heading(s, "Direct Impact on Target Users", C1, BODY_Y, CW);
  textBox(s, bullets([
    [["ISRO and NRSC analysts: ", true],
     ["plain-English querying replaces manual scene-by-scene inspection in a GIS desktop.",
      false]],
    [["Disaster response (NDRF/SDRF): ", true],
     ["rapid before-and-after assessment of flood, landslide and cyclone imagery — and " +
      "because SAR sees through cloud, it works on the days optical imaging fails.", false]],
    [["Agriculture and land records: ", true],
     ["land-cover and change queries over Cartosat scenes without requiring remote-sensing " +
      "expertise from the officer asking.", false]],
    [["Defence and border monitoring: ", true],
     ["combined optical and radar interpretation, with a written trace behind every " +
      "conclusion.", false]],
    [["Students and researchers: ", true],
     ["an accessible entry point to India's Earth-observation archive.", false]],
  ]), { x: C1, y: BODY_Y + 0.3, w: CW, h: 6.2, fontSize: 11, lineSpacing: 13.5 });

  heading(s, "Strategic Impact", C2, BODY_Y, CW);
  textBox(s, bullets([
    [["Lowers the expertise barrier", true],
     [" to India's growing open Earth-observation archive, so more of it actually gets used.",
      false]],
    [["Makes AI output institutionally usable.", true],
     [" An auditable trace is what allows a model's answer to enter an official decision " +
      "record — the gap that blocks AI adoption in government today.", false]],
    [["Builds indigenous capability", true],
     [" in remote-sensing vision-language models rather than depending on foreign " +
      "general-purpose systems, aligning with Atmanirbhar Bharat.", false]],
    [["All-weather capability.", true],
     [" Radar interpretation keeps the system useful during monsoon and cloud cover, when " +
      "optical-only pipelines go blind.", false]],
    [["Extensible to future ISRO sensors", true],
     [" through registry configuration.", false]],
  ]), { x: C2, y: BODY_Y + 0.3, w: CW, h: 6.2, fontSize: 11, lineSpacing: 13.5 });

  heading(s, "Economic and Social Benefits", C3, BODY_Y, CW);
  textBox(s, bullets([
    [["Removes the analyst bottleneck.", true],
     [" Imagery volume grows continuously while trained interpreters do not; querying in " +
      "natural language widens who can extract value from it.", false]],
    [["No procurement burden.", true],
     [" Commodity hardware, open weights, open datasets — deployable without a GPU cluster " +
      "or per-seat licensing.", false]],
    [["Faster disaster assessment", true],
     [" shortens the interval between an event and a resourcing decision, which is where " +
      "relief outcomes are decided.", false]],
    [["Data stays in-country.", true],
     [" Self-hosted inference means sensitive imagery never leaves the institutional " +
      "network.", false]],
    [["Reusable public asset: ", true],
     ["the adapted models and the trace format can be published for other Indian EO " +
      "programmes to build on.", false]],
  ]), { x: C3, y: BODY_Y + 0.3, w: CW, h: BAND - BODY_Y - 0.4, fontSize: 11, lineSpacing: 13.5 });

  // bottom band: why this matters at scale, in one line each
  const stats = [
    ["47", "satellites already open on\nBhoonidhi — the archive this\nsystem is built to unlock"],
    ["4", "sensing capabilities in one\nsystem: VQA, captioning,\nchange, optical+SAR fusion"],
    ["100%", "of model choices are logged\nwith a reason — zero opaque\nselections in the trace"],
    ["0", "GPU clusters required to\ndeploy — runs on commodity\nhardware, self-hosted"],
  ];
  const sw = (W - 0.4) / stats.length;
  stats.forEach(([n, d], i) => {
    const x = 0.2 + i * sw;
    s.addText(n, {
      isTextBox: true, x, y: BAND + 0.18, w: sw - 0.15, h: 0.5, margin: 0,
      fontFace: SERIF, fontSize: 30, bold: true, color: HEAD, align: "center",
    });
    s.addText(d, {
      isTextBox: true, x, y: BAND + 0.72, w: sw - 0.15, h: 0.85, margin: 0,
      fontFace: SANS, fontSize: 9.5, color: INK, align: "center", lineSpacing: 12,
    });
  });
}

/* ==================== SLIDE 6 - RESEARCH AND REFERENCES ================== */
{
  const s = pres.addSlide();
  chrome(s, "RESEARCH AND REFERENCES", 6, { titleSize: 24 });

  const MID = 6.72, ROW = 3.42;
  vrule(s, MID, BODY_Y, BODY_B - 0.02, true);
  hrule(s, 0.15, MID - 0.02, ROW - 0.06, true);
  hrule(s, MID + 0.02, W - 0.15, ROW - 0.06, true);

  heading(s, "Datasets Prescribed by the Problem Statement", 0.2, BODY_Y, 6.3);
  textBox(s, bullets([
    [["BigEarthNet v2.0 / reBEN — ", true],
     ["549,488 co-registered Sentinel-1/2 patch pairs, 19-class CORINE labels. " +
      "arXiv:2407.03653  ·  bigearth.net  ·  CDLA-Permissive-1.0", false]],
    [["VRSBench — ", true],
     ["29,614 images with captions, object references and question-answer pairs. " +
      "arXiv:2406.12384  ·  CC-BY-NC-4.0", false]],
    [["RSVQA (Lobry et al.) — ", true],
     ["low- and high-resolution remote-sensing VQA. Zenodo 6344334 / 6344367  ·  CC-BY-4.0",
      false]],
    [["CDVQA (Yuan et al., IEEE TGRS 2022) — ", true],
     ["change-detection VQA over bi-temporal pairs; imagery from the SECOND dataset.", false]],
  ]), { x: 0.2, y: BODY_Y + 0.3, w: 6.3, h: 2.6, fontSize: 10.5, lineSpacing: 13 });

  heading(s, "Existing Solutions and Competitive Analysis", MID + 0.2, BODY_Y, 6.3);
  textBox(s, bullets([
    [["GeoChat (CVPR 2024) — ", true],
     ["first grounded vision-language model for remote sensing; establishes that domain " +
      "adaptation, not scale, drives accuracy on nadir imagery.", false]],
    [["TEOChat (ICLR 2025) — ", true],
     ["temporal Earth-observation assistant. arXiv:2410.06234", false]],
    [["EarthDial (CVPR 2025) — ", true],
     ["multi-sensory dialogue across RGB, SAR and multispectral inputs.", false]],
    [["GeoPixel (ICML 2025) — ", true],
     ["pixel-level grounding at high resolution. arXiv:2501.13925", false]],
    [["Gap: ", true],
     ["all are single monolithic models. None expose an auditable execution trace or " +
      "validate co-registration before answering — the requirement this problem statement " +
      "is built around.", false]],
  ]), { x: MID + 0.2, y: BODY_Y + 0.3, w: 6.3, h: 2.6, fontSize: 10.5, lineSpacing: 13 });

  heading(s, "Methods and Technology Benchmarking", 0.2, ROW, 6.3);
  textBox(s, bullets([
    [["Domain-adaptive post-training for multimodal models — ", true],
     ["arXiv:2411.19930. Evidence that a small domain-adapted model outperforms a larger " +
      "generic one, which is the basis for our 3B-plus-specialist design.", false]],
    [["reBEN geographic split — ", true],
     ["reduces spatial correlation between train and test, so reported accuracy is honest " +
      "rather than inflated by neighbouring patches.", false]],
    [["SECOND (Yang et al.) — ", true],
     ["4,662 annotated bi-temporal pairs over Hangzhou, Chengdu and Shanghai. " +
      "captain-whu.github.io/SCD/", false]],
    [["SAR radiometric practice — ", true],
     ["decibel conversion with percentile clipping, standard in SAR interpretation and " +
      "essential before any model consumes backscatter.", false]],
  ]), { x: 0.2, y: ROW + 0.3, w: 6.3, h: 3.2, fontSize: 10.5, lineSpacing: 13 });

  heading(s, "Operational and Policy Context", MID + 0.2, ROW, 6.3);
  textBox(s, bullets([
    [["Bhoonidhi (ISRO/NRSC) — ", true],
     ["open dissemination of Earth-observation data from 47 satellites, including " +
      "Cartosat-2S optical and EOS-04 (RISAT-1A) SAR products in GeoTIFF. " +
      "bhoonidhi.nrsc.gov.in", false]],
    [["Indian Space Policy 2023 — ", true],
     ["mandates open dissemination of EO data, which is what makes an assistant over that " +
      "archive worth building now.", false]],
    [["EOS-04 handbook (NRSC) — ", true],
     ["product levels and radiometric conventions that determine correct SAR preprocessing.",
      false]],
    [["Evaluation protocol: ", true],
     ["accuracy reported on RSVQA and CDVQA test splits, and a three-way ablation " +
      "(optical-only, SAR-only, fused) on the BigEarthNet geographic test split as direct " +
      "evidence for cross-modal benefit.", false]],
  ]), { x: MID + 0.2, y: ROW + 0.3, w: 6.3, h: 3.2, fontSize: 10.5, lineSpacing: 13 });
}

const OUT = "SatQueryAI-SIH2026-Idea-Submission.pptx";
pres.writeFile({ fileName: OUT }).then(() => console.log("WROTE " + OUT));
