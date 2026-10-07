# Cactus persona pool export: draft (phase1_safe → persona_redteam)

Status: **DRAFT.** The exporter skeleton, the mapping spec, the validator and the
tests exist. The final 2,000-row pool has **not** been generated. Unresolved
field mappings stay TODO until Jinkwon confirms them.

## 1. Goal

The fork's `main` (`bdc8dd9`, Jinkwon's `persona_redteam`) consumes
`persona_redteam/personas/cactus_distress_n2000.jsonl`, but the repo has no script
that produces it. Its README says so directly. §9 step 5: "reproduce the
negative-attitude filter, thought dedup and existing 2,000-row selection from the
official Cactus data … the previous processing code was removed and must be
re-implemented with a new data-preparation tool." This draft is that tool's data
layer. It only formats source-derived persona data. It has no goal, prompt, model
or evaluation logic.

## 2. Evidence used

| Source | What it establishes |
|---|---|
| persona_redteam README §3.2 | Steps: (1) `attitude == negative` → 9,469; (2) normalized-thought dedup → 4,011; (3) distress-cue ranking → top 2,000; (4) background and chief complaint extracted from intake, with original thought, patterns and utterance examples kept. Field list: `persona_id, descriptor, background, condition, thought, patterns, cognitive_distortion, style_reference, distress_tags, resistance`. Tags and `resistance` are "rule-derived". "Changing the source order or fixed processing rules may change the selected 2,000." |
| persona_redteam `DATA_MANIFEST.json` | Pool: 2,000 rows, 2,550,191 bytes, sha256 `09796d4c…a80`; source `github.com/coding-groot/cactus` |
| Consumer code (loader lines only) | `persona_id` must be a unique non-empty string. `descriptor`, `condition`, `cognitive_distortion` and `style_reference` are read with `.get(f, "")` inside f-strings, so a JSON `null` would render as the text "None". |
| PCSA (EMNLP 2026) §3.2, Fig. 2, §4.2 | Persona = client characteristics plus original-dialogue style references. Fig. 2 example fields: *Persona* (name, Negative, "Foster care history"), *Style Ref* (one quoted real utterance), *Condition* ("Deep feelings of worthlessness; resists standard advice"). Cactus "distress-oriented interactions with stronger negative client tendencies". |
| Cactus (EMNLP 2024 Findings) §3.1, App. E.1, Fig. 16, Table 8 | Intake form (Schmidgall-style): basic info, presenting problem, reason for seeking counseling, past history, academic/occupational functioning, social support. Attitude: positive/neutral/negative. **Table 8: the "negative" attitude was generated with instructions including "showing resistance or defensiveness", topic-shifting, sarcasm, hopelessness and pessimism about therapy.** |
| `archive/285dd23-before-rewrite` `build_personas.py` | Old formats: `descriptor = "a {age}-year-old {gender} {occupation}"`, `cognitive_distortion = "{patterns[0]}: {thought[:160]}"` |

**Correction to earlier docs.** The handoff said "negative attitude ≠ resistance".
More precisely, Cactus negative dialogues were *generated under* resistance-related
behavior instructions (Table 8). The label is a generation condition, not
per-dialogue evidence that resistance occurs. `phase1_safe` therefore still records
resistance only from observed turns (`unknown` by default).

## 3. Reproduction check on the pinned Cactus revision

Source: HF `LangAGI-Lab/cactus` @ `237cb781…`, sha256 `be342149…` (see
`docs/PHASE1_CACTUS_PROFILE.md`).

| README step | phase1_safe | Result |
|---|---|---|
| 31,577 rows | adapter | 31,577 ✅ |
| (1) negative → 9,469 | `attitudes=negative` | 9,469 ✅ |
| (2) normalized-thought dedup → 4,011 | `--dedup thought` (keep earliest row) | **4,011 ✅**. Raw, stripped, lowercased and punctuation-free normalizations all give 4,011, so the undefined normalization does not matter here. |
| (3) distress ranking → top 2,000 | **not implemented** | ❓ rule not documented |
| (4) background / condition extraction | intake sections kept verbatim (`adapter_version phase1-safe-v1`) | mapping ❓ |

Intake coverage on the 4,011: presenting_problem 4,011 · past_history 4,011 ·
functioning 3,997 · social_support 3,975 · family_details 3,264 ·
marital_status 3,129 · education 2,857. 580 of the 4,011 are under 18.

Size hint only, not evidence for any mapping: the dry run without the 5 unresolved
fields averages 463 bytes/row. The existing pool averages 1,275 bytes/row.

## 4. Field mapping status (`phase1_safe/mappings/redteam_pool_draft.json`)

| Field | Draft strategy | Status |
|---|---|---|
| `persona_id` | copy `p1-cactus-NNNNNN` | ⚠️ OPEN: existing derived files (e.g. `outputs/goal_pathology_persona_routed_n813.jsonl`) reference the *old* pool's ids |
| `thought` | copy Cactus `thought` | ✅ verbatim |
| `patterns` | copy Cactus `patterns` | ✅ verbatim |
| `descriptor` | legacy format, nulls dropped (no "person" default) | ⚠️ provisional |
| `cognitive_distortion` | legacy `"{pattern[0]}: {thought[:160]}"` | ⚠️ provisional |
| `condition` | **unresolved**. Candidate: `intake.presenting_problem` (README "주 호소 문제", PCSA "Condition") | ❓ Q1 |
| `background` | **unresolved**. Candidates: `intake.family_details / past_history / social_support / occupation / education / marital_status` | ❓ Q1 |
| `style_reference` | **unresolved**. Candidates: `first_text` or `join_texts` over verbatim client turns | ❓ Q2 |
| `distress_tags` | **unresolved**. Rule-derived per README; rule unknown | ❓ |
| `resistance` | **unresolved**. Rule-derived per README; format unknown (`lexical-v1` is a candidate source) | ❓ |

## 5. Behavior

- Default: export **fails** while any field is unresolved.
- `--on-unresolved omit` is a dry run. Unresolved keys are left out and listed per row in the provenance sidecar.
- Text fields are never written as `null`. A missing source value means the key is omitted (`source_missing` in the sidecar).
- Outputs: `pool.jsonl`, `pool.provenance.jsonl` (persona_id ↔ source_id, versions, seed, omitted fields), `pool.export_manifest.json` (input/mapping/output sha256, field counts, optional comparison with `DATA_MANIFEST.json` rows/bytes/sha256).
- Byte-identical output for the same inputs and mapping.

```bash
python3 -m phase1_safe.run build --input data/raw/cactus.json --out-dir runs/pool/build --dedup thought
python3 -m phase1_safe.export_pool --records runs/pool/build/records.jsonl \
    --personas runs/pool/build/personas.jsonl \
    --mapping phase1_safe/mappings/redteam_pool_draft.json \
    --out runs/pool/pool.jsonl --on-unresolved omit
```

## 6. Questions for Jinkwon (blocking)

1. `condition` and `background`: which Cactus intake parts? (presenting problem? family details or past history?)
2. `style_reference`: one client utterance or several joined? Which turns?
3. Step 3 ranking: what distress cues and weights, and how are ties broken?
4. Must the existing 2,000 rows (sha256 `09796d4c…`) be reproduced exactly, including `persona_id`s used by existing derived outputs, or may the pool be regenerated?
5. `distress_tags` and `resistance`: rules and value format?
6. Minors (580 of 4,011 are under 18): included in the existing pool? Exclude?
7. Any surviving copy of the old producer script?
