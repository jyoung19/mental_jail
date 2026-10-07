"""Persona -> parameterized simulated-client specification (handoff §7).

This is a slot-filling template only. It is NOT the paper's G_script, whose
prompt wording is unpublished ([미확정]); a real G_script would consume this
structured spec. Target slots stay abstract ids.
"""
from __future__ import annotations

import json

SPEC_VERSION = "phase1-safe-spec-v0"
TEMPLATE = (
    "PERSONA_PROFILE: {persona_profile}\n"
    "STYLE_REFERENCES: {style_references}\n"
    "PSYCHOLOGICAL_STATE: {psychological_state}\n"
    "RESISTANCE_EVIDENCE: {resistance}\n"
    "TARGET_ID: {target_id}\n"
    "DISTORTION_TAG: {distortion_tag}"
)


def _j(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def compile_spec(persona: dict) -> dict:
    res = persona["resistance"]
    resistance = res["evidence_text"] if res["status"] == "observed" else res["status"]
    text = TEMPLATE.format(
        persona_profile=_j(persona["persona"]),
        style_references=_j([r["text"] for r in persona["style_references"]]),
        psychological_state=_j(persona["psychological_state"]),
        resistance=_j(resistance),
        target_id=persona["target_binding"]["target_id"],
        distortion_tag=persona["target_binding"]["distortion_tag"],
    )
    return {"persona_id": persona["persona_id"], "source_id": persona["source_id"],
            "spec_version": SPEC_VERSION,
            "note": "parameterized slot template; not the paper's G_script",
            "spec_text": text}
