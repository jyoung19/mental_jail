"""Distress-oriented selection + seed-controlled sampling, with statistics.

The paper (PCSA §4.2) says only "distress-oriented interactions with stronger
negative client tendencies"; the exact rule is [미확정]. The default here is the
provisional, documented rule: Cactus ``attitude == "negative"`` and the source
provides a thought, at least one pattern, and at least one client turn. Every
dropped record is counted by reason.
"""
from __future__ import annotations

import random
from collections import Counter

from .adapters.cactus import dialogue_fingerprint

DEFAULT_ATTITUDES = ("negative",)


def describe_rule(attitudes, require_thought, require_patterns) -> str:
    parts = [f"attitude in {sorted(attitudes)}" if attitudes else "any attitude"]
    if require_thought:
        parts.append("thought present")
    if require_patterns:
        parts.append("patterns present")
    parts.append(">=1 client turn")
    parts.append("dedup by source_id and dialogue text")
    return "; ".join(parts)


def select_records(records, *, attitudes=DEFAULT_ATTITUDES, require_thought=True,
                   require_patterns=True):
    stats = Counter(total=len(records))
    kept, seen_ids, seen_dialogues = [], set(), set()
    for r in sorted(records, key=lambda r: r["source_id"]):
        if r["source_id"] in seen_ids:
            stats["dropped_duplicate_source_id"] += 1
            continue
        seen_ids.add(r["source_id"])
        fp = dialogue_fingerprint(r)
        if r["dialogue"] and fp in seen_dialogues:
            stats["dropped_duplicate_dialogue"] += 1
            continue
        seen_dialogues.add(fp)
        if attitudes and r.get("attitude") not in attitudes:
            stats["dropped_attitude"] += 1
        elif require_thought and not r.get("thought"):
            stats["dropped_missing_thought"] += 1
        elif require_patterns and not r.get("patterns"):
            stats["dropped_missing_patterns"] += 1
        elif not any(t["speaker"] == "client" for t in r["dialogue"]):
            stats["dropped_no_client_turn"] += 1
        else:
            kept.append(r)
    stats["kept"] = len(kept)
    return kept, dict(stats)


def sample_records(records, n, seed):
    """Deterministic in (input set, n, seed); independent of input order."""
    ordered = sorted(records, key=lambda r: r["source_id"])
    if n is None or n >= len(ordered):
        return ordered
    picked = random.Random(seed).sample(ordered, n)
    return sorted(picked, key=lambda r: r["source_id"])
