> **SUPERSEDED v1 — DO NOT USE THESE COMMANDS FOR NEW RUNS.**
> This document records the superseded v1 execution path. The protected old pilot
> directory `persona_redteam/outputs/phase1_public_pilot12_approved` must not be reused.
> Current execution behavior is governed by
> [persona_redteam/docs/PHASE1_SOURCE_CONTRACT.md](PHASE1_SOURCE_CONTRACT.md).
> Any new validation pilot must use a new run directory.

# Public-Code Phase I Execution

## Scope and evidence

This runner connects the available public Phase-I code on `repro/phase1-main`.
It is a new, source-grounded reconstruction, not recovery of the missing
historical Cactus 2,000, JMIR 652, or their routed-candidate artifacts.
The completed earlier source audit remains in `PHASE1_REPRODUCTION.md`.

The paper's [Section 3.2](https://arxiv.org/html/2604.04842v2#S3.SS2)
combines persona information, dialogue-style examples, and a target-to-distortion
mapping. Its Section 4.2 uses Cactus, CBT-DP, Cheeseburger Therapy, and curated
targets. The current repository's VERA/JMIR choices are an adaptation. Adaptive
resistance strategies belong to Phase II; a non-null `resistance` column alone
does not establish paper fidelity.

## Reused implementation

| Component | Provenance and behavior |
| --- | --- |
| Raw preparation | Existing `cactus_prepare.py` and `source_prepare.py`; pinned SHA256/schema/count checks |
| Client filter | Existing `goals/filter_client_utterances.py` system prompt and first 400 characters; explicit yes/no decisions |
| Goal profile | Existing `extraction/extract_goal_pathology.py` prompt, fields, and first 400 characters |
| Retrieval | Existing `matching/match_pathology.py` descriptor formatting, 600-character limit, label routing, VERA risk filters, cosine rank, top 3 |
| Persona construction | PR #2 default `BUILD_SYSTEM`, `EDIT_FIELDS`, and `persona_context`, adapted into `phase1_builder.py` |

Main baseline: `bdc8dd9e031c84f3c6c72fd60c2093f8aa8b53be`.
Builder source: commit `c5051f36caa3fce1eb031fb44dc10b323ca61b15`,
`persona_redteam/experiments/pcsa_embedded_multiturn.py`.
Full upstream source SHA256:
`03eef9eff567f331183a4e8c1bf738adebecf9e41a40accbf90c58eb19a19180`.

The runner chooses the first retrieved candidate, as that upstream builder does.
It does not claim optimal attack performance or clinical appropriateness.
The clinical-history invention variant and Phase-II optimization are excluded.
The original builder's VERA context-field list is preserved; age/gender/risk
are not separately added to that list. Retain the full selected source persona
for auditing any generated claims.

Two existing modules were made reusable: importing the client filter no longer
starts API calls or reads credentials, and retrieval's text/ranking functions
can run with supplied pools and vectors. Its ranking/formatting rules remain
the same. Vector validation rejects shape mismatches, NaNs, and zero vectors.

## Reconstruction mode

`public-code-reconstruction-cactus4011-jmir813-v1` uses:

- All 4,011 Cactus candidates, preserving source-row and duplicate provenance.
  No historical top-2,000 ranking is guessed or applied.
- The exact native VERA-MH SI 100-persona TSV.
- The reconstructed 813 crisis rows, with `jmir-source-` IDs and full original
  goal text. Neither historical JSONL bytes nor historical `jmir-test-` IDs
  are claimed to have been recovered completely.
- By default, the first two source-order rows in each of six labels: 12 pilot
  inputs. This is a new pilot selection before client filtering; the old
  request/disclosure-balanced pilot is not being reproduced. `--per-label 0`
  explicitly selects all crisis rows for a separately authorized larger run.

Pipeline: pilot selection → new client classification → goal profiles →
embedding retrieval → first candidate → upstream Phase-I persona builder.
There are no counselor/target-model calls or Phase-II adaptation calls.

Missing Cactus resistance/tag fields remain null. Generated persona summaries
and client turns are model outputs, not quoted patient records or verified
clinical facts. A completed run is marked `generated_pending_source_fidelity_review`.
Review background, diagnoses, risk, source style, and unsupported additions
before treating generated text as a research input.

## Commands

Run all Python inside `jylim_ARR`, with bytecode disabled. Preparation is offline:

```bash
docker exec -w /workspace/mental_jail_phase1_main jylim_ARR bash -lc '
PYTHONDONTWRITEBYTECODE=1 python3 -B -m persona_redteam.phase1_reproduce prepare \
  --raw /workspace/mental_jail/data/raw/cactus.json \
  --source-dir persona_redteam/outputs/source_prepare \
  --run-dir persona_redteam/outputs/phase1_public_pilot12_approved \
  --per-label 2
'
```

Preparation refuses an existing directory. The prepared directory already exists;
inspect it without inference using:

```bash
docker exec -w /workspace/mental_jail_phase1_main jylim_ARR bash -lc '
PYTHONDONTWRITEBYTECODE=1 python3 -B -m persona_redteam.phase1_reproduce plan \
  --run-dir persona_redteam/outputs/phase1_public_pilot12_approved
'
```

The user approved only this 12-input run, at most 54 attempts and $0.25 estimated
cost. Run the following in your own interactive server terminal. The Python
process prompts for the key with echo disabled; do not paste a key into commands
or chat. No credential file or exported environment variable is used:

```bash
docker exec -it -w /workspace/mental_jail_phase1_main jylim_ARR bash -lc '
set +x
ulimit -c 0
env -u OPENAI_API_KEY PYTHONDONTWRITEBYTECODE=1 python3 -B -m persona_redteam.phase1_reproduce run \
  --run-dir persona_redteam/outputs/phase1_public_pilot12_approved \
  --execute --prompt-api-key --max-requests 54 --max-cost-usd 0.25
'
```

No key value is printed, recorded in manifests, or supplied in command arguments.
The key reference is cleared in `finally`, including errors, and the process
exits after the run. Python cannot guarantee overwriting every copy of an
immutable string in RAM. Core dumps are disabled by the command. Non-TTY input
and getpass's echo-enabled fallback are rejected. Privileged server users can
still inspect process memory; this is not isolation from the server administrator.
The old prepared `phase1_public_pilot12` is retained unchanged; updated code
hashes require the new `_approved` directory.
Omitting `--execute` only displays the plan. API execution uses the existing
OpenAI endpoints; it does not require a GPU or new packages.

## Request budget, checkpoints, and outputs

| Stage | Model | Maximum requests for the 12-input pilot |
| --- | --- | ---: |
| Client classification | `gpt-4o-mini` | 12 |
| Goal profile extraction | `gpt-4o-mini` | 12 |
| Embeddings, batches of 256 | `text-embedding-3-small` | 18 |
| Phase-I persona construction | `gpt-4o-mini-2024-07-18` | 12 |
| Total | | 54 |

Maximum chat output allowance is 13,800 tokens. Rejected client inputs reduce
later requests. Pool embedding text is 2,452,774 UTF-8 bytes. GPT-4o-mini's
standard input/output prices are $0.15/$0.60 per million tokens, and embedding
input is $0.02 per million tokens, checked against the official
[chat model](https://developers.openai.com/api/docs/models/gpt-4o-mini) and
[embedding model](https://developers.openai.com/api/docs/models/text-embedding-3-small)
pages on 2026-10-08. Text tokenization makes actual cost differ from byte estimates.

The cost guard reserves an intentionally conservative byte-based input estimate
plus maximum output before each call; $0.25 is the proposed estimated-cost
budget, not a provider-enforced billing limit. Prior reservations and all
attempts survive resume; cached responses consume no additional requests.
Budgets cannot be increased for an existing run. No automatic retry or HTTP
redirect is allowed. Actual model identifiers, token usage, estimated cost from
reported tokens, and response/failed-or-uncertain statuses are retained. A
failed request may have been billed even if no token usage was received.

Before hidden key input, all pilot goals, pool embedding inputs, and possible
builder contexts are checked for common email/phone/SSN/credential patterns and
structured name/address labels. The prepared real inputs have no matches.
Outgoing requests are checked again before checkpointing/sending. This is a
limited pattern check, not a guarantee of anonymity. Necessary public-source
clinical content remains in requests; full source rows and provenance metadata
are not sent as additional fields. Authentication is never in request receipts.

Inputs and implementation hashes are pinned in `manifest.json`. Any code/input
change requires a fresh run. Each request is checkpointed before sending, and
response checksums are verified on reuse. An uncertain request is not retried
automatically. Invalid classifications are errors, not silently excluded rows.
Truncated/refused generations and malformed vectors stop the run. A file lock
prevents simultaneous execution of the same run.

All research payloads stay under ignored `persona_redteam/outputs/`. Successful
execution adds `client_decisions.jsonl`, `client_goals.jsonl`,
`goal_pathology.jsonl`, `routed_candidates.jsonl`, `phase1_personas.jsonl`,
request/response receipts, and `run_summary.json`. Historical canonical filenames
and committed manifests are not overwritten.

## Validation status

92 offline tests pass: the previous 62 plus 30 integration/checkpoint/budget tests.
The synthetic end-to-end test produces 12 explicitly marked fixture personas
and 36 candidate links, checks both routing pools, and verifies replay makes no
new requests. These fixture outputs are not research results.

Real-source preparation verified 31,577 raw Cactus rows, 9,469 negative rows,
4,011 unique candidates, VERA 100, JMIR 2,046 → 813, and the new 12-input pilot.
All inputs and outputs are Git-ignored. One pre-existing unclosed-file warning
remains in the persona extraction loader. No live inference has been run at
this preparation checkpoint; the approved run awaits interactive API-key input.
