"""Distress-oriented selection + seed-controlled sampling, with statistics.

The paper (PCSA §4.2) says only "distress-oriented interactions with stronger
negative client tendencies"; the exact rule is [미확정]. The default here is the
provisional, documented rule: Cactus ``attitude == "negative"`` and the source
provides a thought, at least one pattern, and at least one client turn. Every
dropped record is counted by reason.

Cactus has several dialogues per client (same intake form + thought, different
CBT technique: 9,469 negative dialogues, ~4,012 clients). With ``dedup_client``
(default) only the dialogue with the smallest source_id is kept per client, so
one persona = one client.
"""
from __future__ import annotations

import random
from collections import Counter

from .adapters.cactus import dialogue_fingerprint

DEFAULT_ATTITUDES = ("negative",)


def client_key(record):
    intake = record.get("intake_form") or {}
    return tuple(intake.get(f) for f in ("name", "age", "gender", "occupation", "reason_for_seeking_help")) + (
        record.get("thought"),)


def _age(record):
    age = (record.get("intake_form") or {}).get("age")
    return int(age) if isinstance(age, str) and age.isdigit() else None


def describe_rule(attitudes, require_thought, require_patterns, dedup_client=True, min_age=None) -> str:
    parts = [f"attitude in {sorted(attitudes)}" if attitudes else "any attitude"]
    if require_thought:
        parts.append("thought present")
    if require_patterns:
        parts.append("patterns present")
    parts.append(">=1 client turn")
    parts.append("dedup by source_id and dialogue text")
    if dedup_client:
        parts.append("one dialogue per client (intake+thought), smallest source_id")
    if min_age is not None:
        parts.append(f"numeric source age >= {min_age}")
    return "; ".join(parts)


def select_records(records, *, attitudes=DEFAULT_ATTITUDES, require_thought=True,
                   require_patterns=True, dedup_client=True, min_age=None):
    stats = Counter(total=len(records))
    kept, seen_ids, seen_dialogues, seen_clients = [], set(), set(), set()
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
        elif min_age is not None and (_age(r) is None or _age(r) < min_age):
            stats["dropped_age"] += 1
        elif dedup_client and client_key(r) in seen_clients:
            stats["dropped_duplicate_client"] += 1
        else:
            seen_clients.add(client_key(r))
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
