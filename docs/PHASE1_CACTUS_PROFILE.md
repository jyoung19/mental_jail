# Phase 1 — Cactus corpus profile (handoff §11.2)

Aggregate counts only; no dialogue text. Reproduce:

```bash
mkdir -p data/raw && curl -L -o data/raw/cactus.json \
  https://huggingface.co/datasets/LangAGI-Lab/cactus/resolve/237cb781cb6cbab609bc11f02a24ea6bc408ea4b/cactus.json
python3 -m phase1_safe.run profile --input data/raw/cactus.json --out-dir runs/phase1_safe/profile
```

**Source:** HF `LangAGI-Lab/cactus` (redirected from `DLI-Lab/cactus`), license GPL,
revision `237cb781cb6cbab609bc11f02a24ea6bc408ea4b`, `cactus.json` sha256
`be3421495f9dd76dd47d5fd4abd9fdabed9c97fcb7f7bba34ecfc78fe07d3d18`.
Raw keys: `thought, patterns (list), intake_form (text), cbt_technique, cbt_plan, attitude, dialogue (text)`.
LLM-generated CBT dialogues — not real patient transcripts. No row id → `source_id = cactus-<row index>`.

## Format check — adapter assumptions confirmed

| Check | Result |
|---|---|
| Rows / parse errors / schema-invalid | 31,577 / 0 / 0 |
| Dialogue speakers | only `Counselor:` / `Client:`; 21–35 turns (median 31) |
| Intake coverage (non-null) | name 31,577 · age 31,577 · gender 31,538 · occupation 24,517 · reason 31,577 |
| Occupation nulls (7,060) | all genuine source placeholders (`Not specified` 4,744, `Undisclosed` 1,605, `Unknown`, `N/A`, …) — not parse misses |
| Gender nulls (39) | source `n/a`, `unknown`, `na` |
| Client utterance length | 8–455 chars, median 130 |

## Distribution

| Item | Value |
|---|---|
| attitude | negative 9,469 · neutral 10,882 · positive 11,226 |
| Unique clients (intake + thought) | 4,057 overall · **4,012 negative** |
| Dialogues per negative client | up to 6 (same client, different `cbt_technique`) |
| Negative clients by age | 10s 716 · 20s 916 · 30s 999 · 40s 729 · 50s 341 · 60s 149 · 70s 149 · 80s 13 |
| **Minors** (negative clients) | **581 under 18, 193 under 13** |
| Gender (negative clients) | female 2,040 · male 1,963 · other/null 9 |
| Pattern labels (negative clients) | overgeneralization 2,598 · fortune-telling 1,895 · personalization 1,843 · mental filtering 1,779 · labeling 1,712 · catastrophizing 1,546 · discounting positive 1,526 · all-or-nothing 1,449 · mind reading 1,135 · `none` 245 · should statements 166 |

`patterns` is a multi-label list (1–9 labels, median 4); the label `none` always
co-occurs with other labels and is kept verbatim as a source label.

## Pilot build (default rule, n=150, seed=0)

`31,577 → drop attitude 22,108 → drop duplicate client 5,457 → 4,012 kept → 150 sampled`.
150 distinct clients/thoughts; occupation present 122/150; byte-identical on re-run.
With `--min-age 18`: 3,431 kept.

## Findings that changed the code

1. **Several dialogues per client** → added one-dialogue-per-client dedup (default).
2. **Resistance heuristic v0 was noisy** ("what's the point" = hopelessness, "didn't help" =
   past attempts) and missed curly apostrophes (`don’t`) → `lexical-v1`. Real data:
   1,064 / 31,577 dialogues flagged; still provisional, default remains `unknown`.
3. **Minors present** → `--min-age` option; inclusion is a team / ethics decision.

## Open decisions for the team

- Include under-18 personas or `--min-age 18`?
- Keep one dialogue per client, or treat each CBT-technique dialogue as a separate persona?
- Use resistance `lexical-v1` at all, or leave `unknown` until a validated method exists?
