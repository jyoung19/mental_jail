"""Corpus profiling report (handoff §11.2): counts and coverage, no generation."""
from __future__ import annotations

from collections import Counter
from statistics import median, quantiles

from .extract import extract_resistance
from .schema import INTAKE_FIELDS, validate_record


def _dist(values):
    if not values:
        return None
    q = quantiles(values, n=4) if len(values) >= 2 else [values[0]] * 3
    return {"n": len(values), "min": min(values), "p25": q[0], "median": median(values),
            "p75": q[2], "max": max(values)}


def profile_records(records: list[dict], parse_errors: int = 0) -> dict:
    attitudes = Counter(r.get("attitude") or "null" for r in records)
    intake_cov = {f: sum(1 for r in records if r["intake_form"].get(f)) for f in INTAKE_FIELDS}
    pattern_counts = Counter(p for r in records for p in r.get("patterns", []))
    client_lens = [len(t["text"]) for r in records for t in r["dialogue"] if t["speaker"] == "client"]
    turn_counts = [len(r["dialogue"]) for r in records]
    lexical = Counter(extract_resistance(r, "lexical-v0")["status"] for r in records)
    return {
        "records": len(records),
        "parse_errors": parse_errors,
        "schema_invalid": sum(1 for r in records if validate_record(r)),
        "no_dialogue_turns": sum(1 for n in turn_counts if n == 0),
        "attitude_counts": dict(sorted(attitudes.items())),
        "negative_records": attitudes.get("negative", 0),
        "intake_field_coverage": intake_cov,
        "thought_coverage": sum(1 for r in records if r.get("thought")),
        "pattern_coverage": sum(1 for r in records if r.get("patterns")),
        "pattern_label_counts": dict(pattern_counts.most_common()),
        "turns_per_dialogue": _dist(turn_counts),
        "client_utterance_chars": _dist(client_lens),
        "resistance_lexical_v0": dict(lexical),
    }
