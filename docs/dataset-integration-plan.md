> **Scope decision (made 2026-09-06):** doing **Phases 0, 1, and 3 only** — the
> "benchmark first, then wire into the demo" recommended slice. **Phase 2
> (training on the official dataset) is explicitly skipped** — the existing
> Step 7 model (`models_weights/landcover_fused.pt`, ablation table already in
> `models_weights/ablation_table.csv`) stays as-is and is not retrained. This
> keeps the already-working demo safe with the hackathon deadline one day out.
>
> **Not started yet** — this is the next thing to pick up.

# Plan — Use the official BigEarthNet.txt dataset

**Goal:** put the hackathon's officially-named dataset (`BigEarthNet.txt`) behind the model we demo, starting with a real benchmark number and adding real trained answers if time allows.

**Deadline reality:** internal round is 7 Sept (tomorrow). Plan is staged so **Phase 1 alone is a complete, presentable win** — Phases 2 and 3 are upside, each with a hard stop point.

---

## The key finding (already verified, not assumed)

`BigEarthNet.txt` is **annotations only** — one 1.4 GB parquet, no imagery. Its schema is:

```
ID, s1_name, patch_id, input, output, type, category, split,
latitude, longitude, country, season, climate_zone
```

`patch_id` and `s1_name` are **the identical keys** the BEN_14k Kaggle dataset uses. Verified against live sample rows — BigEarthNet.txt row 0 and BEN_14k's metadata both carry:

- `patch_id = S2A_MSIL2A_20170613T101031_N9999_R022_T33UUP_26_57`
- `s1_name = S1B_IW_GRDH_1SDV_20170612T165809_33UUP_26_57`

**Consequence: we do not need the 110 GB BigEarthNet v2.0 archive, the LMDB, or the `rico-hdl` tool.** We join the annotations onto the ~13.7k BEN_14k images we already know how to download. Its `S1S2-10m20m` band preset (`VV, VH, B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12`) is also the exact 12 channels our fused model already takes.

License: CDLA-Permissive-1.0 (same as BEN_14k) — clean to use and cite.

## What the dataset actually asks (9,553,962 annotations)

| category | count | answerable by our trained encoder? |
|---|---:|---|
| **presence** | 1,391,053 | **Yes, directly** — "is there X?" maps to class X's score |
| season | 463,662 | Yes, with a small new head |
| climate zone | 463,637 | Yes, with a small new head |
| country | 463,274 | Yes, with a small new head |
| area | 1,390,845 | No — needs quantitative area output |
| count | 1,390,730 | No — needs object counting |
| adjacency | 1,222,128 | No — needs spatial relations |
| point | 1,143,883 | No — needs grounding |
| reference | 1,061,803 | No — needs referring-expression detection |
| relative pos | 99,015 | No — needs spatial relations |
| captioning (`category=None`) | 463,932 | No — needs a language decoder |

Types: `binary` 3,625,160 · `mcq` 3,259,184 · `bounding box` 2,205,686 · `captioning` 463,932
Splits: `train` 4,674,281 · `validation` 2,454,690 · `test` 2,409,962 · `bench` 15,029

**This table is itself a PPT slide** — it states precisely which official benchmark tasks the architecture addresses and which are declared future work, instead of a vague "we used the official dataset."

---

## Phase 0 — Set up and gate (~30 min, Colab)

New notebook: `notebooks/02_bigearthnet_txt_benchmark.ipynb`. Colab again (fast downloads, big disk, optional GPU) — same pattern that worked for Step 7.

1. Download `BigEarthNet.txt.parquet` (1.4 GB) from HF `BIFOLD-BigEarthNetv2-0/BigEarthNet.txt`.
2. Re-download BEN_14k images (~5.5 GB, `narendraaironi/bigearthnet-14k`) via the Kaggle CLI — reuse the working auth + download cells from `01_bigearthnet_encoder.ipynb`.
3. Upload `models_weights/landcover_fused.pt` (94 MB) + `landcover_fused_classes.json` from this machine.
4. **Gate — print these before continuing:**
   - count of BEN_14k patch_ids on disk
   - count of those present in BigEarthNet.txt
   - of those, count of `category=presence` + `type=binary` rows in `test` (and separately in `bench`)

   **Stop condition:** if fewer than ~500 usable presence questions land, stop and reassess rather than reporting a number off a tiny sample. (Expected: ~10k+, since 13.7k patches × ~20 annotations each × ~15% presence × ~25% test.)

## Phase 1 — Benchmark the model we already trained (~2 h) ← *the deliverable*

Evaluates the **existing** `landcover_fused.pt` against official questions. No training.

1. Filter annotations to: `patch_id ∈ images_on_disk`, `type == 'binary'`, `category == 'presence'`, `split ∈ {test, bench}`.
2. Parse the queried land-cover class out of each `input` string and match it (normalized) against our 19 CORINE class names. Report the **match rate**; score only matched questions and state that number openly.
3. **One forward pass per unique patch, not per question** (many questions share a patch — dedupe first, then look up). Keeps this to minutes even on CPU.
4. Answer each question: `sigmoid_score[matched_class] >= 0.5` → `"yes"` else `"no"`; compare to the `output` column.
5. Report: overall accuracy, precision/recall/F1 on "yes", a per-class breakdown, the question match rate, and the n used. Separate `test` and `bench` numbers.
6. Save `bigearthnet_txt_benchmark.json` + a markdown table; download both back to the repo.

**Deliverable:** a real, defensible sentence for the PPT — *"On N official BigEarthNet.txt presence questions from the held-out test split, our trained optical+SAR encoder answers X% correctly"* — plus the capability matrix above.

## Phase 2 — SKIPPED for this round (training on the official data)

Not being done before the 7 Sept round — see the scope decision note at the top. Left here for reference in case there's time later:

Two options, cheapest first. **Do 2a or 2b, not both.**

- **2a — Fine-tune on `presence` questions.** Same fused encoder, but supervised by the official train-split presence answers instead of the CORINE labels. Directly optimizes for the benchmark being reported. Re-run Phase 1 after to show a before/after delta.
- **2b — Add season / climate-zone / country heads.** Three small classification heads sharing the frozen encoder (4 seasons, ~10 countries, N climate zones). Turns three more official categories from ❌ to ✅ in the matrix. Slightly more code, still a few hours.

Save any new weights as `landcover_fused_bentxt.pt` (+ classes json) — **do not overwrite** the Step 7 checkpoints, so the demo always has a known-good fallback.

## Phase 3 — Wire it into the live demo (~1 h, only if Phase 1 done)

Makes the browser demo answer real yes/no questions instead of returning the placeholder.

- `satquery/models/landcover.py`: add `answer_presence_question(manifest_path, modality, question)` — runs the classifier, parses a known class from the question, returns `{answer: yes/no, matched_class, score, stub: False}`, or `None` if no class matches.
- `satquery/agent/nodes.py`: in the `vqa`/`captioning` branch, try presence-answering **before** falling through to the existing `landcover.predict()` → stub chain. Existing behaviour is preserved whenever the question isn't a presence question.
- `tests/test_landcover.py`: add cases for a matching question, a non-matching question (must return `None`), and the no-weights path (must still degrade cleanly).
- Copy `bigearthnet_txt_benchmark.json` into the repo so the numbers ship with the code.

---

## Risks and how each is handled

| risk | handling |
|---|---|
| BEN_14k ∩ BigEarthNet.txt overlap too small | Explicit gate in Phase 0 with a stop condition — found before any work is wasted |
| Class-name parsing from question text is imperfect | Report match rate; score only matched questions; never silently drop |
| Colab hands out a CPU runtime again (happened in Step 7) | Phase 1 is inference-only and fine on CPU; assert device early and only insist on GPU for Phase 2 |
| Running out of time mid-Phase-2 | Phase 2 writes to new filenames; Step 7 checkpoints and the working demo are never touched |
| Overclaiming in the PPT | The capability matrix ships with the number — state plainly which categories are unaddressed and why |

## Honest framing for the PPT

State all three plainly:
1. The official dataset **is** used — for evaluation, and (if Phase 2 lands) for training.
2. Images come from the BEN_14k subset, not the full 110 GB archive — a scale limitation, not a correctness one, and the join key is the dataset's own `patch_id`.
3. The encoder addresses the `presence` category (+ season/climate/country if 2b lands); `area`, `count`, `adjacency`, `point`, `reference`, `relative pos` and `captioning` are unaddressed and named as future work.
