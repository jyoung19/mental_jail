"""Canonical schemas for Phase 1 safe records and their validators.

Two record kinds (docs/PHASE1_HANDOFF.md §6.1, §7):

- CounselingRecord: dataset-agnostic view of one source dialogue (adapter output).
- Phase1Persona: the persona specification emitted by this module.

Records are plain dicts so they round-trip through JSONL unchanged; the
validators return a list of error strings (empty = valid).
"""
from __future__ import annotations

import re

SCHEMA_VERSION = "phase1-safe-schema-v0"
ADAPTER_VERSION = "phase1-safe-v0"

SPEAKERS = ("client", "counselor")
RESISTANCE_STATUS = ("observed", "not_observed", "unknown")
AFFECT_STATUS = ("observed", "unknown")
PERSONA_FIELDS = ("age", "gender", "occupation", "reason_for_seeking_help")
INTAKE_FIELDS = ("name", "age", "gender", "occupation", "reason_for_seeking_help")

PLACEHOLDER_TARGET_ID = "<ABSTRACT_TARGET_ID>"
PLACEHOLDER_DISTORTION_TAG = "<DISTORTION_TAG>"
# Abstract identifiers only: short, no whitespace, so a natural-language request
# cannot be smuggled in as a target id.
TARGET_ID_RE = re.compile(r"^(<ABSTRACT_TARGET_ID>|[A-Za-z0-9][A-Za-z0-9_.:-]{0,63})$")
# Distortion tags look like Cactus pattern labels ("jumping to conclusions: mind reading").
DISTORTION_TAG_RE = re.compile(r"^(<DISTORTION_TAG>|[a-z][a-z0-9 _:/-]{0,63})$")


def _is_str_or_none(v):
    return v is None or isinstance(v, str)


def validate_record(r: dict) -> list[str]:
    errs = []
    for key in ("source_id", "dataset"):
        if not isinstance(r.get(key), str) or not r[key]:
            errs.append(f"{key}: required non-empty string")
    turns = r.get("dialogue")
    if not isinstance(turns, list):
        errs.append("dialogue: required list")
        turns = []
    for i, t in enumerate(turns):
        if not isinstance(t, dict):
            errs.append(f"dialogue[{i}]: expected object")
            continue
        if t.get("turn_id") != i:
            errs.append(f"dialogue[{i}].turn_id: expected {i}")
        if t.get("speaker") not in SPEAKERS:
            errs.append(f"dialogue[{i}].speaker: {t.get('speaker')!r} not in {SPEAKERS}")
        if not isinstance(t.get("text"), str):
            errs.append(f"dialogue[{i}].text: required string")
    intake = r.get("intake_form")
    if not isinstance(intake, dict):
        errs.append("intake_form: required object")
    else:
        for f in INTAKE_FIELDS:
            if f not in intake:
                errs.append(f"intake_form.{f}: missing (use null when absent)")
            elif not _is_str_or_none(intake[f]):
                errs.append(f"intake_form.{f}: string or null")
    for key in ("attitude", "thought", "reframed_thought"):
        if key not in r:
            errs.append(f"{key}: missing (use null when absent)")
        elif not _is_str_or_none(r[key]):
            errs.append(f"{key}: string or null")
    if not isinstance(r.get("patterns"), list) or not all(isinstance(p, str) for p in r.get("patterns", [])):
        errs.append("patterns: required list of strings")
    return errs


def validate_persona(p: dict) -> list[str]:
    errs = []
    for key in ("persona_id", "source_id", "dataset", "schema_version"):
        if not isinstance(p.get(key), str) or not p[key]:
            errs.append(f"{key}: required non-empty string")
    persona = p.get("persona")
    if not isinstance(persona, dict):
        errs.append("persona: required object")
    else:
        for f in PERSONA_FIELDS:
            if f not in persona:
                errs.append(f"persona.{f}: missing (use null when absent)")
            elif not _is_str_or_none(persona[f]):
                errs.append(f"persona.{f}: string or null")
    refs = p.get("style_references")
    if not isinstance(refs, list):
        errs.append("style_references: required list")
    else:
        for i, ref in enumerate(refs):
            if not (isinstance(ref, dict) and isinstance(ref.get("turn_id"), int)
                    and isinstance(ref.get("text"), str) and ref.get("source_id") == p.get("source_id")):
                errs.append(f"style_references[{i}]: needs int turn_id, text, matching source_id")
    state = p.get("psychological_state")
    if not isinstance(state, dict):
        errs.append("psychological_state: required object")
    else:
        if not _is_str_or_none(state.get("thought")):
            errs.append("psychological_state.thought: string or null")
        if not isinstance(state.get("patterns"), list):
            errs.append("psychological_state.patterns: required list")
        affect = state.get("affect")
        if not isinstance(affect, dict) or affect.get("status") not in AFFECT_STATUS:
            errs.append(f"psychological_state.affect.status: one of {AFFECT_STATUS}")
    res = p.get("resistance")
    if not isinstance(res, dict) or res.get("status") not in RESISTANCE_STATUS:
        errs.append(f"resistance.status: one of {RESISTANCE_STATUS}")
    else:
        ids, texts = res.get("evidence_turn_ids"), res.get("evidence_text")
        if not isinstance(ids, list) or not isinstance(texts, list) or len(ids) != len(texts):
            errs.append("resistance: evidence_turn_ids/evidence_text must be equal-length lists")
        elif res["status"] == "observed" and not ids:
            errs.append("resistance: status=observed requires evidence")
        elif res["status"] != "observed" and ids:
            errs.append("resistance: evidence present but status is not observed")
    tb = p.get("target_binding")
    if not isinstance(tb, dict):
        errs.append("target_binding: required object")
    else:
        if not isinstance(tb.get("target_id"), str) or not TARGET_ID_RE.match(tb["target_id"]):
            errs.append("target_binding.target_id: must be an abstract id")
        if not isinstance(tb.get("distortion_tag"), str) or not DISTORTION_TAG_RE.match(tb["distortion_tag"]):
            errs.append("target_binding.distortion_tag: must be a short label")
    prov = p.get("provenance")
    if not isinstance(prov, dict) or not isinstance(prov.get("seed"), int) or not prov.get("selection_rule"):
        errs.append("provenance: requires selection_rule and int seed")
    return errs
