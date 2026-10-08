# Phase-1 Reproduction Record

## Baseline and scope

Current-main baseline: `bdc8dd9e031c84f3c6c72fd60c2093f8aa8b53be`.
Local reproduction branch: `repro/phase1-main`.
Worktree: `/workspace/mental_jail_phase1_main` inside `jylim_ARR`.

This record separates verified public-source transformations from historical
artifact identity. Matching counts alone does not establish byte-identical
rendering, historical selection, or historical model decisions. No final
Cactus 2,000-persona artifact or new JMIR client-classification decisions were
generated. Neither README was changed.

## 1. EXACT REPRODUCTION

### Cactus raw input and deterministic candidate stage

Official source: `LangAGI-Lab/cactus`, revision
`237cb781cb6cbab609bc11f02a24ea6bc408ea4b`, file `cactus.json`.
The verified input is `/workspace/mental_jail/data/raw/cactus.json`.
It contains 31,577 records and has SHA256:

```text
be3421495f9dd76dd47d5fd4abd9fdabed9c97fcb7f7bba34ecfc78fe07d3d18
```

The top-level JSON list contains objects with string fields `thought`,
`intake_form`, `dialogue`, `attitude`, `cbt_technique`, and `cbt_plan`, plus
`patterns` as a list of strings. Cactus is generated dialogue, not a corpus
of actual patient records.

| Stage/category | Records |
| --- | ---: |
| Raw | 31,577 |
| Negative attitude | 9,469 |
| Neutral attitude | 10,882 |
| Positive attitude | 11,226 |
| Unique negative normalized thoughts | 4,011 |
| Duplicate negative rows | 5,458 |

Normalization is exactly `" ".join(thought.split())`: collapse whitespace,
preserving case and punctuation. Exact-string uniqueness is also 4,011;
normalization introduces no additional merges in this corpus. The first
negative row in raw order represents each normalized-thought group. All
duplicate source-row indices are retained as provenance.

These verified counts and the explicit current candidate-selection rule are
deterministic. They do not recover an undocumented historical normalization,
representative-row choice, or final persona rendering.

### Historical pre-rewrite 150-persona artifact

At commit `285dd23df6c66ed16fe86bf01ad5e5284530feab`, the audited files are
`harmful_behavior_collection/data/personas.jsonl` and
`harmful_behavior_collection/build_personas.py`.
All 150 personas map uniquely to raw Cactus rows: 0 ambiguous, 0 unmapped.
The historical builder reproduced its 94,078-byte artifact byte-for-byte:

```text
7799800b2e84023f72b43f7e31e254fc7b4468941dc9662bff4434158192d643
```

Recovered builder rules:

- Scan raw rows in order; require negative attitude, nonempty
  whitespace-normalized thought, and nonempty patterns.
- Extract age, gender, and occupation using the historical single-line intake
  regex. Missing values become empty strings; empty occupation becomes
  `person`. Placeholder strings are not converted to null.
- Construct `a {age}-year-old {gender} {occupation}`, replace doubled spaces,
  and strip surrounding whitespace. Deduplicate by this descriptor string,
  not by thought.
- Assign `cac-{accepted_index:03d}`, starting with `cac-000`.
- Preserve the raw pattern list. Construct `cognitive_distortion` from the
  first pattern, `": "`, and the first 160 characters of normalized thought.
  Store thought truncated to 200 characters.
- Select the first physical dialogue line containing literal `Client:`;
  take the text after that label, collapse whitespace, and truncate to 200
  characters. Store source as `cactus-negative`.

The old intake regex can capture a following field label as occupation:
raw row 45 (`cac-006`) captures `Education:`. This historical behavior was
observed, not adopted as a new parsing rule. These old 150-persona rules do
**not** establish later current-main top-2,000 selection or ranking.

### VERA-MH SI acquisition

Official source: `SpringCare/VERA-MH`, pinned revision
`546e431f532389684f8b581a8ec1d83d86ad12d1`, file `data/SI/personas.tsv`.
The native TSV reproduces `personas/veramh_si_n100.tsv` exactly:

- 100 rows, 100 unique names, 19 native columns preserved unchanged.
- Risk counts: None 10, Low 30, High 30, Immediate 30.
- Byte size: 169,377.
- SHA256: `07f0aa92cde50469d18aff640ed03e0df93e8863aed75ea102e4ba97a124330b`.

This is an exact byte-for-byte reproduction, not a schema conversion.

## 2. SOURCE-GROUNDED RECONSTRUCTION

### Cactus candidate rendering and compatibility

`cactus_prepare.py` produces an unranked `cactus-candidate-v1` pool. Each row
includes `persona_id`, `source_id`, `source_row_index`, `source`,
`normalized_thought`, `descriptor`, `background`, `condition`, `thought`,
`patterns`, `cognitive_distortion`, `style_reference`,
`style_reference_turn_id`, `intake`, `dialogue`, `distress_tags`, `resistance`,
`unresolved_fields`, and `provenance`.

Candidate IDs are `candidate-cactus-{raw_row_index:06d}`. Full raw thought,
intake background, and patterns are preserved. Explicit demographic fields
are parsed with missing/placeholder values converted to null. Descriptor
uses available age/gender/occupation key-value pairs; cognitive distortion
joins patterns. Style reference is the first parsed client turn, without
historical truncation. Unknown distress tags and resistance remain null.
These are transparent source renderings, not recovered historical wording.

Qualified labels such as `Client (sighs):` and `Client (sarcastically):`
retain their parenthetical qualifier at the beginning of utterance text.
Recognized speaker names remain restricted to client/patient and
counselor/counsellor/therapist; genuine unlabeled continuation lines attach
to the preceding turn. No qualifier receives a new semantic interpretation.
Current-main `load_source("cactus")` and `load_pools()` accept synthetic rows
using this candidate schema structurally, without API or embedding calls.

### JMIR official inputs and exact alignment

Official repository: `ellisalicante/LLMs-Mental-Health-Crisis`, revision
`91032137b958bd4c69dbf703b91eb753a59909ba`.

| Pinned source file | SHA256 |
| --- | --- |
| `data/processed/sampled_dataset_n_2046_nPerD168_seed0.json` | `a4cacb7f899b7d99e1acbfce995eafa6325735d47e19cb2f2f0c04063614b344` |
| `data/llm_label/gpt-4o-mini-labeled-sampled_dataset_n_2046_nPerD168_seed0-merged-labels.json` | `ff1ade27018fb30a1d07377664778f4652c57a90d64641c3db4e260986e9fb6f` |

Both files contain 2,046 rows. Source and merged labels align exactly by row
position, `dataset_id`, and ordered `inputs`. All 2,046 composite conversation
keys `(dataset_id, tuple(inputs))` are unique; `dataset_id` alone identifies
a corpus, not a conversation.

The historical ID convention is strongly supported as
`jmir-test-{original_test_row_index:04d}` by recovered upstream PR #2 examples:

| Historical ID | Verified crisis label |
| --- | --- |
| `jmir-test-0000` | `suicidal_ideation` |
| `jmir-test-0007` | `anxiety_crisis` |
| `jmir-test-0013` | `substance_abuse_or_withdrawal` |
| `jmir-test-0070` | `self-harm` |

This confirms the recoverable examples, not every absent historical row.
The standalone reconstruction deliberately retains its local positional IDs,
`jmir-source-{original_test_row_index:04d}`, and stores the source row index.

The `source_hf` alias mapping is recovered from upstream `src/load_datasets.py`:

| Dataset alias | Hugging Face source repository |
| --- | --- |
| `hugg_1` | `sajjadhadi/Mental-Disorder-Detection-Data` |
| `hugg_2`, `hugg_6` | `marmikpandya/mental-health` |
| `hugg_3` | `fadodr/mental_health_dataset` |
| `hugg_4` | `fadodr/mental_health_therapy` |
| `hugg_5` | `psycode1/psyset` |
| `hugg_7` | `Amod/mental_health_counseling_conversations` |
| `hugg_8` | `cypsiSAS/transformed_Suicidal_ideation` |
| `hugg_9` | `fanyin3639/test_test_self_harm_all_levels` |
| `hugg_10` | `arianaazarbal/self-harm-synthetic-eval` |
| `hugg_11` | `richie-ghost/suicidal_finetune` |
| `hugg_16k` | `ShenLab/MentalChat16K` |
| `hugg_100k` | `jerryjalapeno/nart-100k-synthetic` |

Twelve aliases contribute 168 rows each; `hugg_11` contributes 30.

### JMIR crisis filtering and rendering limits

The 813 subset removes only `no_crisis` and missing labels, preserving original
order, row objects, source positions, and IDs. No client-utterance classifier
is applied.

| Label | Full 2,046 | Crisis 813 |
| --- | ---: | ---: |
| `suicidal_ideation` | 380 | 380 |
| `no_crisis` | 1,231 | 0 |
| `anxiety_crisis` | 177 | 177 |
| `substance_abuse_or_withdrawal` | 77 | 77 |
| `self-harm` | 139 | 139 |
| `violent_thoughts` | 21 | 21 |
| `risk_taking_behaviours` | 19 | 19 |
| Missing (`null`) | 2 | 0 |

Local reconstruction preserves ordered `inputs`, `dataset_id`,
`source_row_index`, and `original_label` alongside `goal_id`, `goal`,
`crisis_label`, and `source_hf`. `goal` is a newline join without text stripping
or rewriting. JSONL uses UTF-8, `json.dumps(..., ensure_ascii=False)`, insertion
field order, and a final LF. This explicit wire format is not historical.

| Local reconstruction | Bytes | SHA256 |
| --- | ---: | --- |
| 2,046 rows | 2,340,916 | `b06ed87481e76c4d6ba7957f28517ac08614d8a0f35bd69aaeea91f88145e5a9` |
| 813 rows | 987,065 | `f75aee3e42e889c98f21a1cbc42c9a9e48e5973fb976611aa8b9cc342cf4c920` |

Bounded historical reconstruction tested the minimal documented schema
`goal_id`, `goal`, `crisis_label`, `source_hf`, using supported `jmir-test-`
IDs and two upstream-supported scalar renderings:

| Goal rendering, 2,046 rows | Bytes | SHA256 |
| --- | ---: | --- |
| Newline-joined inputs | 1,191,277 | `53e0dd097a896fe0f71dd35a41ac956851b1232db442ecbe9ecc93ff1f6ce295` |
| JSON array rendered as a string | 1,244,513 | `7c098e1bc58547a04644dd10b52a11477c180235d9eba890383191a9ff19e20c` |

Neither matched. A diagnostic JSON-encoded joined string was excluded from
the supported candidates after inspection of the upstream call chain.
No arbitrary serialization tuning or blind permutation search was performed.
Official source alignment, labels, order, and deterministic filtering reproduce;
historical byte-identical importer artifacts do not.

## 3. HISTORICALLY UNRECOVERABLE / BLOCKED

| Historical manifest target | Rows | Bytes | SHA256 |
| --- | ---: | ---: | --- |
| `personas/cactus_distress_n2000.jsonl` | 2,000 | 2,550,191 | `09796d4c70cbd8567955ec9d29096843ded565e7a89718b231e393f6d229ea80` |
| `goals/crisis_goals_jmir_n2046.jsonl` | 2,046 | 2,406,201 | `df04f0e1740618d01c9260d5884916fab5fc0e9c1caefcd721d63609081c0422` |
| `goals/crisis_goals_jmir_n813.jsonl` | 813 | 1,024,402 | `879ca00b9e57e7ffc62a2fcaa19dc5186572fd5790ac5f2f2f79938383d4c09a` |

- **Cactus:** the historical 4,011 → 2,000 distress ranking, authentic
  membership/order, and final rendering/tagging conventions are unavailable.
  The old 150-persona builder cannot establish them. Production preprocessing
  stops at the 4,011-candidate pool; exact top-2,000 reproduction is not claimed.
- **JMIR importer:** historical schema/rendering is unavailable. Matching
  source counts and labels does not recover missing content or serialization
  choices. Neither historical JSONL hash matches; canonical JMIR files have
  not been populated with nonmatching reconstructions.
- **JMIR 813 → 652:** the retained GPT-4o-mini client-classification decisions
  are unavailable. Current README counts for 652 are historical reference
  metadata, not newly reproduced decisions. Rerunning classification would
  not establish historical identity and was not attempted.

Authentic historical artifacts, retained importer code, ranking logic, or
classification decisions are needed to resolve these gaps.

## Implementation and validation

- `persona_redteam/cactus_prepare.py`: pinned hash/schema validation,
  deterministic negative filtering and thought grouping, source-grounded
  candidate extraction, and a future historical-artifact validator reporting
  hashes, size, rows, IDs, schema, candidate mappings, recoverable source rows,
  thought set/order, and fields that cannot map exactly.
- `persona_redteam/source_prepare.py`: pinned source validation, native VERA
  acquisition, verified JMIR positional joining, deterministic crisis filtering,
  and explicit manifest mismatch reporting.
- `persona_redteam/tests/test_cactus_prepare.py`: 21 tests covering schema,
  normalization, filtering, duplicates, determinism, nulls, speaker qualifiers,
  continuation behavior, historical validation, and loader compatibility.
- `persona_redteam/tests/test_source_prepare.py`: 13 source-preparation tests.

Generated research payloads remain Git-ignored and uncommitted. Nonmatching
JMIR reconstructions and source caches stay under
`persona_redteam/outputs/source_prepare/`; verified VERA is an ignored native
TSV. No historical Cactus top-2,000 payload is created.

Offline validation totals **62 passing tests, 0 failures, 0 errors**:
21 Cactus preparation, 13 source preparation, 11 existing persona-pilot,
and 17 existing surrogate-selection tests. Loader smoke tests perform no
model/API inference. Existing loaders emit unclosed-file `ResourceWarning`s;
their implementation was not changed.

All Python runs inside `jylim_ARR`, with `PYTHONDONTWRITEBYTECODE=1` and
`python3 -B`. No GPU, model inference, or package installation is needed.
Run the complete suite from the host with:

```bash
docker exec -w /workspace/mental_jail_phase1_main jylim_ARR bash -lc '
set -eu
mkdir -p persona_redteam/outputs/source_prepare/test_tmp
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR=/workspace/mental_jail_phase1_main/persona_redteam/outputs/source_prepare/test_tmp
python3 -B -m unittest persona_redteam.tests.test_cactus_prepare persona_redteam.tests.test_source_prepare -v
cd persona_redteam
python3 -B -m unittest discover -s experiments -p "test_*.py" -v
python3 -B -m unittest discover -s matching -p "test_*.py" -v
rmdir outputs/source_prepare/test_tmp
'
```

## Bounded reproducibility claim

The public-source portion of Phase 1 is reproduced exactly where sufficient
source and transformation information exists. VERA-MH reproduces byte-for-byte;
Cactus reproduces the verified counts through an explicit deterministic
4,011-candidate stage. JMIR reproduces official source alignment, labels,
source positions, counts, and deterministic 813 filtering; the supported
historical ID convention matches recoverable examples. Historical artifacts
depending on removed importer logic, retained LLM decisions, or an unavailable
top-2,000 ranking remain blocked rather than reconstructed speculatively.
