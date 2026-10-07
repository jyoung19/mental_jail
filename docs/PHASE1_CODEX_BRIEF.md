# Phase 1 — Repository Analysis Brief (pre-work for Codex)

> Read-only analysis of the repo at `285dd23` against `docs/PHASE1_HANDOFF.md`.
> No code was changed. Purpose: let the next agent skip the exploration step and
> start from a reviewed plan.

## 1. What already exists for Phase I

| Piece | Where | Status vs handoff §4.1 |
|---|---|---|
| Cactus → persona builder | `harmful_behavior_collection/build_personas.py` | Exists, but not paper-grounded enough (see §2) |
| Persona file (150) | `harmful_behavior_collection/data/personas.jsonl` | Keys: `persona_id, descriptor, cognitive_distortion, style_reference, patterns, thought, source` — **no source_id, no seed, no provenance** |
| Loaders | `common/data_sources.py` (`load_personas`, `load_attack_goals`, `build_cases`) | Default `DATA_DIR` = `<repo>/data/`, which **does not exist** in the repo (data lives in `harmful_behavior_collection/data/`) |
| Persona↔goal matching | `common/data_sources.py::_match_persona_order` (embedding cosine) | Matching rule is [미확정] in the paper; treat as current team choice |
| `T(y→C_dist)`, `G_script` | `phase1_persona_perturbation/phase1_persona.py` (`generate_distortion`, `scriptwrite`) | LLM-generated; prompt wording is the repo's own, **not** the paper's |
| Surrogate hill-climbing | `phase1_persona.py::harden_persona`, `run_phase1.py` | Extension beyond paper §3.2 — must not be called "exact Phase I" |
| Goals | `harmful_behavior_collection/data/attack_goals_v4.jsonl` (576) | Current CARES-free set; v2 deprecated (`data/DEPRECATED_v2.md`) |
| Tests | — | **None** in the repo |

## 2. Gaps in `build_personas.py` vs handoff §4.1 / §7

1. **No `source_id`** — Cactus row index/ID is dropped; provenance cannot be traced.
2. **No seed** — takes the first N negative rows in file order; selection is deterministic but not seed-controlled or logged.
3. **Dedup by descriptor string** (`"a 41-year-old female ..."`) — silently drops distinct dialogues; no stats recorded.
4. **No filtering statistics** — counts of total / negative / missing-thought / dup are not reported.
5. **Intake parsing** — only age/gender/occupation; `reason_for_seeking_help` not extracted; missing occupation becomes `"person"` (fabricated default — handoff says use `null`).
6. **Style reference** = first client line truncated to 200 chars; single example, no turn_id.
7. **Distortion** = `patterns[0] + thought[:160]` merged into one string (mixes source label with free text).
8. **No resistance field** — handoff requires `observed|not_observed|unknown` + evidence turn ids.
9. **No target_binding** — persona and goal are only joined later in `build_cases`.
10. Flat imports (`import data_sources`) — only runs with `common/` on `PYTHONPATH`.

## 3. Method inconsistency to resolve (do not pick silently)

- `METHOD.md` / `docs/STATUS.md §1`: "fully on-target, surrogate-free".
- `docs/STATUS.md §3` (v4, 2026-10-07): Phase 1 was run with open surrogate `PsychoCounsel-Llama3-8B` (570/576 hardened).
- → Phase 1 safe module should **not** depend on either; record the chosen mode in a run manifest.

## 4. Proposed Phase 1 safe module (for approval — not implemented)

New, additive files; existing code untouched:

```
phase1_safe/
  schema.py          # canonical CounselingRecord + Phase1Persona dataclasses, validate()
  adapters/cactus.py # raw Cactus row -> CounselingRecord (keeps source_id, null for missing)
  extract.py         # persona fields, style refs (with turn_id), state metadata,
                     # resistance evidence (default status=unknown; rule-based only if agreed)
  select.py          # seed-controlled distress/negative filter + filter statistics
  compile_spec.py    # parameterized template only (<PERSONA_PROFILE> ... <DISTORTION_TAG>)
  manifest.py        # run manifest: seed, adapter_version, input hash, counts
  run_phase1_safe.py # CLI: --input --out --seed --n --style-k
tests/
  fixtures/synthetic_counseling.jsonl   # benign, hand-made, no real corpus
  test_schema.py  test_cactus_adapter.py  test_select_determinism.py  test_no_harmful_text.py
```

Open parameters (keep as CLI args, defaults marked provisional):
`n`, `style_k` (number of style refs), negative/distress filter rule,
resistance rule (or `unknown` only), dedup key.

## 5. Test plan (handoff §11.1–11.3)

1. `pytest tests/` on synthetic fixture: required fields, source_id preserved,
   same seed ⇒ identical output, different seed ⇒ may differ, missing fields stay `null`.
2. Profiling report on real Cactus (local only, not committed): counts per attitude,
   filter pass rate, intake/pattern coverage, style length distribution.
3. Manual audit of ~20 personas: every field traceable to source.
4. Fixed-sequence pilot — **blocked** until Jinkwon's Phase II interface arrives.

## 6. Questions blocking further work

- Jinkwon: file names/branch/format/source/license of persona & query data; what "다른 데이터셋" means (persona corpus vs goal set vs v4).
- Is CBT-DP / Cheeseburger Therapy in scope for the first adapter, or Cactus only?
- Resistance evidence: rule-based extraction, LLM-tagged, or `unknown` for now?
- Branch name: keep `repro/phase1-safe`?
