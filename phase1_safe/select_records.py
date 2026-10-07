"""Distress-oriented selection + seed-controlled sampling, with statistics.

The paper (PCSA §4.2) says only "distress-oriented interactions with stronger
negative client tendencies"; the exact rule is [미확정]. The default here is the
provisional, documented rule: Cactus ``attitude == "negative"`` and the source
provides a thought, at least one pattern, and at least one client turn. Every
dropped record is counted by reason.

Cactus has several dialogues per client (same intake form + thought, different
CBT technique: 9,469 negative dialogues, ~4,012 clients). ``dedup`` picks how
duplicates collapse; in every mode the record with the smallest source_id (=
earliest row in the source file) is kept:

- ``client`` (default): one dialogue per client (intake fields + thought).
- ``thought``: one dialogue per normalized thought (lowercase, collapsed
  whitespace). This is step 2 of the persona_redteam README §3.2 Cactus pool
  (9,469 -> 4,011). The README does not define "normalized"; on the pinned
  Cactus revision raw, stripped, lowercased and punctuation-free variants all
  give 4,011, so the choice does not change the count there.
- ``none``: keep every dialogue.
"""
from __future__ import annotations

import random
import re
from collections import Counter

from .adapters.cactus import dialogue_fingerprint

DEFAULT_ATTITUDES = ("negative",)
DEDUP_MODES = ("client", "thought", "none")


def client_key(record):
    intake = record.get("intake_form") or {}
    return tuple(intake.get(f) for f in ("name", "age", "gender", "occupation", "reason_for_seeking_help")) + (
        record.get("thought"),)


def normalized_thought(record):
    return re.sub(r"\s+", " ", record.get("thought") or "").strip().lower()


_DEDUP_KEYS = {"client": client_key, "thought": normalized_thought}


def _age(record):
    age = (record.get("intake_form") or {}).get("age")
    return int(age) if isinstance(age, str) and age.isdigit() else None


def describe_rule(attitudes, require_thought, require_patterns, dedup="client", min_age=None) -> str:
    parts = [f"attitude in {sorted(attitudes)}" if attitudes else "any attitude"]
    if require_thought:
        parts.append("thought present")
    if require_patterns:
        parts.append("patterns present")
    parts.append(">=1 client turn")
    parts.append("dedup by source_id and dialogue text")
    if dedup == "client":
        parts.append("one dialogue per client (intake+thought), smallest source_id")
    elif dedup == "thought":
        parts.append("one dialogue per normalized thought (lowercase, collapsed whitespace), smallest source_id")
    if min_age is not None:
        parts.append(f"numeric source age >= {min_age}")
    return "; ".join(parts)


def select_records(records, *, attitudes=DEFAULT_ATTITUDES, require_thought=True,
                   require_patterns=True, dedup="client", min_age=None):
    if dedup not in DEDUP_MODES:
        raise ValueError(f"dedup must be one of {DEDUP_MODES}")
    key_fn = _DEDUP_KEYS.get(dedup)
    stats = Counter(total=len(records))
    kept, seen_ids, seen_dialogues, seen_keys = [], set(), set(), set()
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
        elif key_fn and key_fn(r) in seen_keys:
            stats[f"dropped_duplicate_{dedup}"] += 1
        else:
            if key_fn:
                seen_keys.add(key_fn(r))
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
