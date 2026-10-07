"""CounselingRecord -> Phase1Persona (docs/PHASE1_HANDOFF.md §5.1, §7).

Only source-supported values are copied. Things the source does not label
(affect) stay ``unknown``. Resistance is ``unknown`` unless the opt-in lexical
heuristic finds client turns that push back on the counselor; that heuristic is
provisional ([미확정]) and its method name is recorded on every persona. Cactus
``attitude == negative`` is NOT treated as resistance.
"""
from __future__ import annotations

import re

from .schema import (ADAPTER_VERSION, PLACEHOLDER_DISTORTION_TAG, PLACEHOLDER_TARGET_ID,
                     SCHEMA_VERSION)

RESISTANCE_METHODS = ("none", "lexical-v1")
# Client pushback on the preceding counselor turn. Provisional, English-only.
# v1 (after checking real Cactus output) drops markers that mostly expressed
# hopelessness or past attempts rather than pushback ("what's the point",
# "didn't help") and matches after normalizing curly apostrophes.
_RESISTANCE_MARKERS = (
    "i don't think that", "i don't think so", "i don't think it will", "that won't work",
    "that wouldn't work", "it won't help", "that won't help", "won't make a difference",
    "i've tried that", "i already tried that", "easier said than done",
    "you don't understand", "that's not true", "i doubt that", "yeah, but", "yes, but",
    "i'm not sure that will", "i'm not sure that would",
)
_MARKER_RE = re.compile("|".join(re.escape(m) for m in _RESISTANCE_MARKERS))


def _norm(text):
    return text.lower().replace("\u2019", "'").replace("\u2018", "'")


def select_style_references(record, k=3, min_chars=20, max_chars=400):
    """First ``k`` client turns whose length is in range, in dialogue order (no truncation)."""
    refs = []
    for t in record["dialogue"]:
        if t["speaker"] == "client" and min_chars <= len(t["text"]) <= max_chars:
            refs.append({"turn_id": t["turn_id"], "text": t["text"], "source_id": record["source_id"]})
            if len(refs) >= k:
                break
    return refs


def extract_resistance(record, method="none"):
    if method == "none":
        return {"status": "unknown", "method": "none", "evidence_turn_ids": [], "evidence_text": []}
    if method != "lexical-v1":
        raise ValueError(f"unknown resistance method {method!r}; choose from {RESISTANCE_METHODS}")
    ids, texts = [], []
    turns = record["dialogue"]
    for prev, t in zip(turns, turns[1:]):
        if t["speaker"] == "client" and prev["speaker"] == "counselor" and _MARKER_RE.search(_norm(t["text"])):
            ids.append(t["turn_id"])
            texts.append(t["text"])
    return {"status": "observed" if ids else "not_observed", "method": method,
            "evidence_turn_ids": ids, "evidence_text": texts}


def build_persona(record, *, seed, selection_rule, style_k=3, style_min_chars=20,
                  style_max_chars=400, resistance_method="none"):
    intake = record["intake_form"]
    return {
        "persona_id": f"p1-{record['source_id']}",
        "source_id": record["source_id"],
        "dataset": record["dataset"],
        "schema_version": SCHEMA_VERSION,
        "persona": {
            "age": intake.get("age"),
            "gender": intake.get("gender"),
            "occupation": intake.get("occupation"),
            "reason_for_seeking_help": intake.get("reason_for_seeking_help"),
        },
        "style_references": select_style_references(record, style_k, style_min_chars, style_max_chars),
        "psychological_state": {
            "thought": record.get("thought"),
            "patterns": list(record.get("patterns") or []),
            "affect": {"value": None, "status": "unknown"},
        },
        "resistance": extract_resistance(record, resistance_method),
        "target_binding": {"target_id": PLACEHOLDER_TARGET_ID, "distortion_tag": PLACEHOLDER_DISTORTION_TAG},
        "provenance": {
            "selection_rule": selection_rule,
            "seed": seed,
            "adapter_version": ADAPTER_VERSION,
            "source_attitude": record.get("attitude"),
            "style_rule": f"first {style_k} client turns with {style_min_chars}-{style_max_chars} chars",
        },
    }
