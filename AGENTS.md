# Working Rules (for Codex / Claude / any coding agent)

## Git
- Never modify, commit to, or push to `main`.
- Do Phase 1 work on a topic branch (planned name: `repro/phase1-safe`; the
  current prep branch is `claude/intelligent-johnson-uqo9eq`). Ask the user if unsure.
- `origin` = `jyoung19/mental_jail` (working fork).
- `upstream` = `dlwlsrnjs/mental_jail` (Jinkwon's original). Fetch only; never push.
- Do not merge or open a PR without explicit user approval.
- Small commits; record data version / schema version / experiment condition in the message.

## Read first (before any Phase 1 change)
1. `docs/PHASE1_HANDOFF.md` — research context and decisions (source of truth).
2. `docs/PHASE1_CODEX_BRIEF.md` — repo analysis already done: gaps, files, plan.
3. `docs/STATUS.md`, `METHOD.md` — existing method/worklog (note: they disagree
   on surrogate usage; see the brief).

## Rules
- Do not invent missing experimental settings, dataset fields, prompts, or
  thresholds. Anything marked [미확정] in the handoff stays a parameter/TODO.
- Distinguish confirmed decisions from assumptions in code comments and docs.
- Do not hardcode or tune toward paper Table 6 numbers.
- Never commit API keys, raw corpora (Cactus/CARES/etc.), restricted harmful-query
  text, or target-model outputs.
- Persona and harmful goal are separate objects; link them only via a binding record
  using abstract `target_id` / `distortion_tag`.
- Before major code changes, explain the planned files and changes and wait for approval.
