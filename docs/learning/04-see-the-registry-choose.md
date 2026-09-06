# 04 — See the registry choose

> **Status:** done. `python -m satquery resolve --capability change_detection --modalities optical_ms --image-count 2` prints a chosen tool plus every rejected candidate and why.

## What we built

Three files under `satquery/registry/`: `schema.py` (a Pydantic `ToolSpec` — what a tool can do, what it needs, how good it claims to be), `loader.py` (reads every YAML file in `registry/entries/`, validates each one against that schema, fails loudly and by name if one is broken), and `resolver.py` (given a capability + modality set + image count, decides which tool answers the query — and writes down why every other candidate did or didn't qualify). Six entries in `registry/entries/*.yaml` give the resolver real filtering and ranking to do: two single-image VQA/captioning/grounding models, a SAR-only captioner, two bi-temporal change-detection specialists, and one optical+SAR fusion tool. Plus `python -m satquery resolve ...` to run it from the command line.

## The one big idea: record the losers, not just the winner

The tempting way to build a resolver is: filter candidates, pick the best one, return its name. That's enough to make the demo *work*, but it's useless for the thing SIH26167 actually grades — capability #5, "an agentic controller producing an auditable execution trace." A trace that only shows the winner tells a judge nothing about whether the system understood the *other* tools exist, or just got lucky. Recording every candidate — including the ones that didn't qualify, with a specific, named reason — is what turns "it picked cdvqa-siamese" into "it correctly ruled out geochat-7b (no change_detection support), rsvqa-baseline (same), sar-captioner-lite (wrong capability), and skysense-fusion (wrong capability), then ranked cdvqa-siamese over diff-unet-baseline on eval score." The second version is a claim a judge can actually verify. The first is just an assertion.

This is exactly the same instinct behind Step 2's validator recording PASS results, not only FATAL ones (`satquery/io/validate.py`): a report that only lists failures proves nothing about what was actually checked. The resolver is that same pattern applied to tool selection instead of file validation — which is why `resolver.py`'s docstring says outright that it mirrors `validate.py` on purpose.

## Filter → rank → record, in that order

```python
# satquery/registry/resolver.py
def _evaluate(spec, capability, modalities, image_count) -> Candidate:
    if capability not in {c.value for c in spec.capabilities}:
        return Candidate(spec.id, ..., eligible=False, reason=f"does not support capability {capability!r} ...")

    missing = [m for m in modalities if m not in {m.value for m in spec.modalities}]
    if missing:
        return Candidate(spec.id, ..., eligible=False, reason=f"missing modality support for {missing} ...")

    if image_count > spec.image_count.max:
        return Candidate(spec.id, ..., eligible=False, reason=f"image_count max {spec.image_count.max} < {image_count}")
    if image_count < spec.image_count.min:
        return Candidate(spec.id, ..., eligible=False, reason=f"image_count min {spec.image_count.min} > {image_count}")

    return Candidate(spec.id, ..., eligible=True, score=spec.eval_scores[capability], reason="eligible: ...")
```

**Filter** runs this check on every registered tool, in a fixed order (capability, then modality, then image count) — so a tool that fails on more than one dimension still gets exactly one clear reason instead of a vague "didn't qualify." **Rank** picks the eligible candidate with the highest declared `eval_scores[capability]`, ties broken by tool id so ranking never depends on float equality or dict ordering. **Record** happens whether or not a candidate passed: `ResolutionResult.candidates` holds every tool that was considered, in registry load order, each tagged eligible or not with its reason. `chosen` is just whichever eligible candidate ranked first — a derived fact, not a separately-tracked value that could drift from the candidate list.

Running the example from the plan:

```
=== Resolve: capability='change_detection' modalities=['optical_ms'] image_count=2 ===
RESULT    TOOL                SCORE  REASON
CHOSEN    cdvqa-siamese       0.67   eligible: capability, modality, and image_count all satisfied (eval_score=0.67)
eligible  diff-unet-baseline  0.44   eligible: capability, modality, and image_count all satisfied (eval_score=0.44)
rejected  geochat-7b          -      does not support capability 'change_detection' (supports ['vqa', 'captioning', 'grounding'])
rejected  rsvqa-baseline      -      does not support capability 'change_detection' (supports ['vqa'])
rejected  sar-captioner-lite  -      does not support capability 'change_detection' (supports ['captioning'])
rejected  skysense-fusion     -      does not support capability 'change_detection' (supports ['cross_modal_fusion', 'vqa'])

Chosen: cdvqa-siamese  (2 eligible, 4 rejected)
```

Note the three different result states, not just pass/fail: **CHOSEN** (the winner), **eligible** (qualified, but outranked — `diff-unet-baseline` really could have handled this query), and **rejected** (didn't qualify, with the specific reason). Collapsing "eligible-but-not-chosen" into "rejected" would hide a genuinely different fact: diff-unet-baseline wasn't *wrong* for this query, it was just worse.

## Why "record every candidate" matters for the auditable-trace requirement

The problem statement's capability #5 doesn't ask for a system that gets the right answer — it asks for one that shows its work well enough that a human can check *why* it did what it did. A resolver that silently returns `"cdvqa-siamese"` passes that bar exactly as often as it happens to be right, which a judge has no way to distinguish from luck. A resolver that returns the full candidate list lets a judge ask "why not skysense-fusion?" and get a real, specific answer (`does not support capability 'change_detection'`) instead of a shrug.

This also has to be *reproducible*, not just informative — reasoning that changes between runs is worse than no reasoning at all, because it means the trace isn't actually describing a deterministic decision process. `resolve()` never touches randomness, and registry load order comes from `sorted(entries_dir.glob(...), key=lambda p: p.name)` in `loader.py` rather than raw filesystem iteration order (which isn't guaranteed stable across OSes). `tests/test_registry.py::test_resolve_is_reproducible_byte_identical_ordering_and_reasoning` calls `resolve()` twice and asserts the candidate list — tool ids, eligibility, and reason strings — is identical both times. That test is the actual proof; everything above is why it needs to pass.

## Loud failure at boot, not a shrug mid-query

```python
# satquery/registry/loader.py
try:
    return ToolSpec.model_validate(raw)
except ValidationError as exc:
    field_errors = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    raise RegistryLoadError(f"{path.name}: schema validation failed - {field_errors}") from exc
```

`ToolSpec` uses `model_config = {"extra": "forbid"}`, so a typo'd field name (`weight` instead of `weights`) fails validation exactly like a wrong type would — YAML has no schema of its own, so nothing else would catch that kind of mistake. Two custom validators go further than what Pydantic's field types alone can express: `image_count.min <= max` (a relationship between two fields, not a property of either alone), and every declared capability having a matching `eval_scores` entry in `[0, 1]` (so the resolver can never crash reaching for a score that doesn't exist — see `tests/test_registry.py::test_malformed_entry_missing_eval_score_for_declared_capability`). The loader also checks two things across the whole registry after every file parses individually: no duplicate `id`, and every `fallback` actually points at a tool that got loaded. All of this runs the moment anything touches `get_registry()` — the CLI's `resolve` command, or later the agent's `plan` node — so a broken entry announces itself immediately, by file and field, instead of surfacing as a mysterious `KeyError` three layers into answering someone's actual question.

## Try it

```bash
./.venv/Scripts/python.exe -m satquery resolve --capability change_detection --modalities optical_ms --image-count 2
./.venv/Scripts/python.exe -m satquery resolve --capability vqa --modalities optical_rgb --image-count 1
./.venv/Scripts/python.exe -m satquery resolve --capability vqa --modalities sar --image-count 5   # nothing qualifies
```

- The last one exercises the empty-result path — `image_count=5` exceeds every tool's `max`, so `Chosen: none`, not a crash.
- `pytest tests/ -v` — 83 tests total (58 from before + 25 new), covering schema validation (missing fields, bad enum values, `min > max`, unknown fields, duplicate ids, dangling fallbacks), the loader picking up every file in a directory, and the resolver's filter/rank/reject logic across several capability-modality-count combinations.
- Open any file in `registry/entries/` — every `eval_scores` number is commented as a placeholder for prototype ranking, not a published benchmark result. `geochat-7b`'s `est_vram_mb: 16000` against the dev laptop's 4 GB RTX 3050 is also the honest reason it's `weights: stub` for this round, not `rsvqa-baseline`.

## Words worth knowing

- **Schema validation** — checking that structured data (here, hand-written YAML) actually matches the shape a program expects, before that program ever tries to use it. Pydantic does this by raising on construction, not by returning `None` or a partially-filled object.
- **Eligibility vs. ranking** — two different questions the resolver answers about a candidate. Eligibility is binary (can this tool even handle the request?); ranking only applies among the eligible ones, and answers a different question (which is best?). Conflating them loses the "eligible but outranked" case, which is real information.
- **Auditable trace** — a record detailed enough that a third party (here, a hackathon judge) can verify a decision was made for the stated reason, not just observe that a decision was made. The bar isn't "produced an answer," it's "produced an answer *and* a reason a stranger can check."
- **Reproducibility** — running the same input twice and getting byte-identical output, including intermediate reasoning, not just the final answer. Without it, "here's why the system chose X" is a description of one run, not a description of the system.

---

**Next:** Step 5 — `satquery/agent/{state,nodes,graph,confidence}.py`, the nine-node pipeline that ties ingest → validate → classify → plan (this registry) → preprocess → execute → fuse → confidence → respond together into one traced, reproducible run.
