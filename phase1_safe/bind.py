"""Attach abstract target bindings to personas (handoff §5.2).

A bindings file is JSONL with ``persona_id`` or ``source_id`` plus ``target_id``
and optional ``distortion_tag``. Only abstract identifiers are accepted; rows
carrying natural-language request fields are rejected so harmful query text
never enters persona/spec artifacts. Matching personas to goals (the paper's
T(y -> C_dist)) is [미확정] and is decided outside this module.
"""
from __future__ import annotations

from .schema import DISTORTION_TAG_RE, PLACEHOLDER_DISTORTION_TAG, TARGET_ID_RE

_ALLOWED_KEYS = {"persona_id", "source_id", "target_id", "distortion_tag", "note_id"}


def validate_binding(row: dict) -> list[str]:
    errs = []
    extra = set(row) - _ALLOWED_KEYS
    if extra:
        errs.append(f"unexpected keys {sorted(extra)} (bindings hold abstract ids only)")
    if not (row.get("persona_id") or row.get("source_id")):
        errs.append("needs persona_id or source_id")
    if not isinstance(row.get("target_id"), str) or not TARGET_ID_RE.match(row["target_id"]):
        errs.append(f"target_id {row.get('target_id')!r} is not an abstract id")
    tag = row.get("distortion_tag", PLACEHOLDER_DISTORTION_TAG)
    if not isinstance(tag, str) or not DISTORTION_TAG_RE.match(tag):
        errs.append(f"distortion_tag {tag!r} is not a short label")
    return errs


def apply_bindings(personas: list[dict], bindings: list[dict]) -> dict:
    """Mutates personas in place; returns counts. Raises on invalid or conflicting rows."""
    by_key = {}
    for i, row in enumerate(bindings):
        errs = validate_binding(row)
        if errs:
            raise ValueError(f"binding[{i}]: " + "; ".join(errs))
        key = ("persona_id", row["persona_id"]) if row.get("persona_id") else ("source_id", row["source_id"])
        if key in by_key:
            raise ValueError(f"binding[{i}]: duplicate binding for {key[0]}={key[1]}")
        by_key[key] = row
    bound = 0
    for p in personas:
        row = by_key.get(("persona_id", p["persona_id"])) or by_key.get(("source_id", p["source_id"]))
        if row:
            p["target_binding"] = {"target_id": row["target_id"],
                                   "distortion_tag": row.get("distortion_tag", PLACEHOLDER_DISTORTION_TAG)}
            bound += 1
    return {"bindings": len(bindings), "personas_bound": bound, "personas_unbound": len(personas) - bound}
