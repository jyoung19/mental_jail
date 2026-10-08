# Phase I source-fidelity contract v2

The completed `phase1_public_pilot12_approved` run failed source-fidelity review:
11 generated records had 0 PASS, 4 REVIEW and 7 FAIL. Do not scale that run.
This contract supersedes the v1 builder/execution instructions in
`PHASE1_EXECUTION.md`. No v2 API pilot has been executed or approved.

## Three independent channels

`source_persona` contains facts assembled locally from the selected source pool
row. `goal_context` retains the separate author's complete goal and the extractor's
**unverified goal-side pathology hypotheses**. `injected_content` contains only
the generated belief, client turns and literal target citations. Neither the
goal nor model output can supply values to `source_persona`.

The model cannot return a biography, `persona_summary`, source overrides, or
arbitrary extra fields. There is no combined `rendered_first_turn`. Source facts
are never paraphrased by the model. The old functions in `phase1_builder.py`
remain for historical audit/tests; the active runner uses `build_locked_messages`
and `assemble_build` from `phase1_source_contract.py`.

## Source facts and evidence

- **VERA:** every native column, including age, gender, background, diagnoses and
  symptoms, current/remote suicidal thoughts and behaviors, both risk fields,
  triggers, treatment engagement/access, disclosure, reaction, communication
  style, stress, support, stigma, discrimination, and seed phrase. Missing required
  fields and placeholders become null, never inferred facts.
- **Cactus:** descriptor, complete intake/background, condition, thought,
  patterns, cognitive distortion, style reference, turn ID and dialogue. Source
  ID, row index, duplicate indexes, preprocessing provenance and a hash of the
  complete selected row are retained. Goal distortions remain in `goal_context`.
- **Style:** source communication evidence is a separate `style_evidence`
  object. Generated turns remain unverified; no claim of measured style fidelity
  is made from copying the evidence.

Every known factual field has its original value and an evidence citation:
`field`, `start`, `end`, `text`. Offsets count Python characters within that field,
with an exclusive end. Structured field citations use canonical JSON of the
selected row's value, not offsets in the original raw file. Placeholder
normalization is deterministic and retains negations and the Cactus `none` label.

The offline validator checks field existence, bounds, exact quoted text, exact
expected values, complete field coverage, source/persona identity and record hash.
A correct quote cannot justify an unrelated rewritten fact. Unknown values have
null evidence. Target citations resolve against the goal only and cannot serve
as persona evidence. These are **structural checks, not semantic proof**.

## Compatibility and acceptance

Narrow first-person patterns extract explicit goal age, gender, diagnosis,
medication, legal/driving context, and selected risk/history statements, with
literal goal citations. The complete goal is checked; the upstream classifier's
400-character input is unchanged.

- `REJECT`: explicit age/gender mismatch or supported contradictory risk/history.
- `REVIEW`: unknown source demographics when the goal specifies them, goal-side
  diagnosis/history needing review, or a minor paired with legal/driving context.
  A minor/context flag is not a claim that conduct is legally impossible.
- `NO_EXPLICIT_CONFLICT`: no conflict found by these limited patterns. This is
  not a compatibility or clinical-fidelity certification.

Both REJECT and REVIEW stop the builder call for that selected candidate. The
runner does not change its identity, rewrite facts, or silently choose a different
candidate. Generated text gets the same narrow checks; flagged generations stay
in `build_rejections.jsonl`, not `phase1_personas.jsonl`.

All other generated records remain `pending_human_review`. Natural-language
ambiguity, causal claims, symptoms, family/life events, target retention and style
still require human review. The rule set does not recognize every possible
wording, and upstream pathology extraction can still produce unsupported
hypotheses; it cannot establish a source diagnosis through this contract.

## Outputs and validation

Future execution requires a **new** prepared directory and separate approval.
The mode is `public-code-reconstruction-cactus4011-jmir813-source-lock-v2`;
implementation hashes include the new contract module. The runner explicitly
rejects the old pilot directory and its descendants, including resolved aliases.

New outputs include `source_contracts.jsonl`, `compatibility_decisions.jsonl`,
and `build_rejections.jsonl`. Existing budget, response cache, hidden-key input,
and no-automatic-retry controls remain. Reassess request sizes/cost and privacy
before any newly approved run because more source fields are now supplied.

120 offline tests pass: all 92 existing tests and 28 new synthetic regressions.
The existing synthetic API fixture was adapted to the strict injected-content
response schema; no existing test was removed. Regressions cover demographic
overwrites, goal-side medication/diagnosis/risk/legal facts, source patterns,
evidence forgery and fact laundering, nulls, channel separation, candidate
identity, style/provenance, compatibility blocking, and old-pilot write protection.
Tests run in `jylim_ARR` with bytecode disabled and socket/API access patched to
fail. No GPU, model/API inference, commit or push is part of this change.
