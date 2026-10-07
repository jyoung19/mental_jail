# phase1_safe — Phase I persona specification pipeline (paper-grounded, safe)

Implements `docs/PHASE1_HANDOFF.md` §4.1 / §7. **Paper-grounded reimplementation,
not an exact PCSA reproduction**: the paper does not publish `G_script`, the
`T(y→C_dist)` mapping, the persona–goal matching rule, sample counts or seeds.
Existing code (`phase1_persona_perturbation/`, `harmful_behavior_collection/`) is untouched.

```
raw corpus (Cactus JSON/JSONL)  ──adapters/cactus.py──▶  CounselingRecord (schema.py)
   ──select_records.py (filter + seed sampling + stats)──▶
   ──extract.py──▶ Phase1Persona ──bind.py (abstract target_id only)──▶ compile_spec.py ──▶ spec
```

## Run (stdlib only, Python ≥3.9, from repo root)

```bash
# 1) corpus profiling — no generation (handoff §11.2)
python3 -m phase1_safe.run profile --input data/raw/cactus.json --out-dir runs/phase1_safe/profile

# 2) build personas + specs
python3 -m phase1_safe.run build --input data/raw/cactus.json --out-dir runs/phase1_safe/build \
    --n 150 --seed 0 [--resistance lexical-v0] [--bindings bindings.jsonl]

# tests (synthetic fixture only)
python3 -m unittest discover -s phase1_safe/tests -t .
```

`build` writes `records.jsonl`, `personas.jsonl`, `specs.jsonl` (byte-identical for
the same input + args) and `manifest.json` (input sha256, args, filter stats,
coverage, timestamp). `runs/` and raw corpora are gitignored — do not commit them.

`--format canonical` accepts already-canonical `CounselingRecord` JSONL; use it for
other corpora (CBT-DP, Cheeseburger Therapy, or Jinkwon's files) after writing an adapter.

## What is decided vs. provisional

| Item | Status | Where |
|---|---|---|
| Persona and goal are separate; link only via abstract `target_id` | 결정 | `bind.py` rejects non-id text and query fields |
| Missing/placeholder source values → `null`, never a default | 결정 | `adapters/cactus.py::clean_value` |
| `attitude=negative` is **not** resistance | 결정 | resistance default `unknown` |
| Affect: Cactus has no label → always `unknown` | 결정 | `extract.py` |
| Filter = negative + thought + patterns + ≥1 client turn | **provisional** | `--attitudes`, `--allow-missing-*` |
| Style refs = first 3 client turns, 20–400 chars | **provisional** | `--style-k`, `--style-*-chars` |
| `lexical-v0` resistance markers (English phrase list) | **provisional, opt-in** | `extract.py::_RESISTANCE_MARKERS` |
| Cactus raw format (`intake_form` text, `Client:` lines) | **assumed** — same as old `build_personas.py`; verify with `profile` on real data | `adapters/cactus.py` |
| `source_id` = `cactus-<row index>` when the row has no id | 결정 (traceable via input sha256) | `to_record` |
| Spec text template | slot template only, **not** paper `G_script` | `compile_spec.py` |

## Not done here (blocked)

- Real-corpus profiling: needs the raw Cactus file locally (not in repo; HF was unreachable from the build env).
- CBT-DP / Cheeseburger adapters: data and field mapping unknown.
- Goal binding / matching rule and fixed-sequence `w/o Phase II` executor: wait for Jinkwon's data and Phase II interface.
