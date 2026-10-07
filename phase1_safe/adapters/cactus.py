"""Cactus raw row -> CounselingRecord.

Assumed raw row shape (same as the existing ``build_personas.py``; verify with
``python3 -m phase1_safe.run profile`` on the real corpus before trusting it):

    {"intake_form": "<free text with 'Age: 41' style fields and numbered sections>",
     "attitude": "negative" | "neutral" | "positive",
     "thought": "...", "patterns": [...] or "a, b",
     "dialogue": "Counselor: ...\\nClient: ...", ...}

Rules: nothing is invented. Fields missing from the source, or filled with a
placeholder such as "Not specified", become null. Cactus is LLM-generated CBT
dialogue, not real patient transcripts.
"""
from __future__ import annotations

import hashlib
import re

DATASET = "cactus"

_SPEAKER_MAP = {"client": "client", "patient": "client",
                "counselor": "counselor", "counsellor": "counselor", "therapist": "counselor"}
_SPEAKER_RE = re.compile(r"^\s*(client|patient|counsel+or|therapist)\s*:\s*(.*)$", re.I)
_KEY_RE = re.compile(r"^\s*([A-Za-z][A-Za-z /()-]{0,40}?)\s*:\s*(.*)$")
_SECTION_RE = re.compile(r"^\s*\d+\s*[.)]\s*(.+?)\s*:?\s*$")
_BASIC_KEYS = {"name": "name", "age": "age", "gender": "gender", "sex": "gender",
               "occupation": "occupation", "job": "occupation"}
# Intake fields beyond the basic persona fields, kept verbatim so downstream
# exporters can choose a mapping (Cactus App. E.1 / Fig. 16 intake layout).
INTAKE_EXTRA_FIELDS = ("education", "marital_status", "family_details", "presenting_problem",
                       "past_history", "functioning", "social_support")
_EXTRA_BASIC_KEYS = {"education": "education", "marital status": "marital_status",
                     "family details": "family_details"}
_SECTION_HEAD_RE = re.compile(r"^\s*\d+\s*[.)]\s*([^:\n]*?)\s*(?::\s*(.*))?$")
_SECTION_TITLES = (("presenting problem", "presenting_problem"), ("past history", "past_history"),
                   ("functioning", "functioning"), ("social support", "social_support"),
                   ("anyone you can talk to", "social_support"))
_PLACEHOLDERS = {"", "-", "n/a", "na", "none specified", "not specified", "unspecified",
                 "undisclosed", "unknown", "not provided", "not mentioned", "not applicable"}


def clean_value(v):
    """Normalize a source value; placeholders become None (never a made-up default)."""
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return None if s.lower().rstrip(".") in _PLACEHOLDERS else s


def parse_intake_form(text) -> dict:
    out = {"name": None, "age": None, "gender": None, "occupation": None,
           "reason_for_seeking_help": None}
    if not isinstance(text, str):
        return out
    lines = text.splitlines()

    def is_header(line):
        m = _KEY_RE.match(line)
        return bool(_SECTION_RE.match(line)) or bool(
            m and (m.group(1).strip().lower() in _BASIC_KEYS or len(m.group(1).split()) <= 3)
            and not m.group(2).strip())

    def is_key_line(line):
        m = _KEY_RE.match(line)
        return bool(m and len(m.group(1).split()) <= 4)

    for i, line in enumerate(lines):
        sec = _SECTION_RE.match(line)
        m = _KEY_RE.match(line)
        if sec and "reason for seeking" in sec.group(1).lower():
            body = []
            for nxt in lines[i + 1:]:
                if _SECTION_RE.match(nxt):
                    break
                body.append(nxt)
            if out["reason_for_seeking_help"] is None:
                out["reason_for_seeking_help"] = clean_value(" ".join(body))
            continue
        if not m:
            continue
        key, value = m.group(1).strip().lower(), m.group(2).strip()
        if "reason for seeking" in key:
            field = "reason_for_seeking_help"
        elif key in _BASIC_KEYS:
            field = _BASIC_KEYS[key]
        else:
            continue
        if not value:
            # Value on the next non-empty line, unless that line is another field/section.
            nxt = next((ln for ln in lines[i + 1:] if ln.strip()), "")
            value = "" if (is_key_line(nxt) or is_header(nxt)) else nxt
        if out[field] is None:
            out[field] = clean_value(value)
    return out


def parse_intake_sections(text) -> dict:
    """Extra intake fields: basic-block keys (education, marital status, family
    details) and numbered section bodies (presenting problem, past history,
    functioning, social support). Text is kept verbatim (whitespace-normalized);
    absent or placeholder sections are None."""
    out = {f: None for f in INTAKE_EXTRA_FIELDS}
    if not isinstance(text, str):
        return out
    current, body = None, []

    def flush():
        if current and out[current] is None:
            out[current] = clean_value(" ".join(body))

    for line in text.splitlines():
        head = _SECTION_HEAD_RE.match(line)
        if head:
            flush()
            title = head.group(1).lower()
            current = next((field for key, field in _SECTION_TITLES if key in title), None)
            body = [head.group(2)] if head.group(2) else []
            continue
        if current:
            body.append(line.strip())
            continue
        m = _KEY_RE.match(line)
        if m and m.group(1).strip().lower() in _EXTRA_BASIC_KEYS:
            field = _EXTRA_BASIC_KEYS[m.group(1).strip().lower()]
            if out[field] is None:
                out[field] = clean_value(m.group(2))
    flush()
    return out


def parse_dialogue(dialogue) -> list[dict]:
    """String ("Speaker: text" lines) or list of {speaker|role, text|content} -> turns."""
    turns = []
    if isinstance(dialogue, list):
        for item in dialogue:
            if not isinstance(item, dict):
                continue
            spk = _SPEAKER_MAP.get(str(item.get("speaker", item.get("role", ""))).strip().lower())
            text = clean_value(item.get("text", item.get("content")))
            if spk and text:
                turns.append({"turn_id": len(turns), "speaker": spk, "text": text})
        return turns
    if not isinstance(dialogue, str):
        return turns
    for line in dialogue.splitlines():
        m = _SPEAKER_RE.match(line)
        if m:
            spk = _SPEAKER_MAP.get(m.group(1).lower(), "counselor")
            turns.append({"turn_id": len(turns), "speaker": spk, "text": m.group(2).strip()})
        elif turns and line.strip():  # continuation of the previous turn
            turns[-1]["text"] = f"{turns[-1]['text']} {line.strip()}".strip()
    for t in turns:
        t["text"] = re.sub(r"\s+", " ", t["text"]).strip()
    turns = [t for t in turns if t["text"]]
    for i, t in enumerate(turns):
        t["turn_id"] = i
    return turns


def parse_patterns(patterns) -> list[str]:
    if isinstance(patterns, str):
        items = patterns.split(",")
    elif isinstance(patterns, list):
        items = patterns
    else:
        items = []
    out = []
    for p in items:
        s = clean_value(p)
        if s and s not in out:
            out.append(s)
    return out


def to_record(row: dict, index: int) -> dict:
    """Convert one raw row. ``index`` is the row position in the input file and is
    used for ``source_id`` only when the row has no id of its own (the manifest
    records the input file hash, so index-based ids stay traceable)."""
    raw_id = row.get("id", row.get("idx"))
    source_id = f"{DATASET}-{raw_id}" if raw_id not in (None, "") else f"{DATASET}-{index:06d}"
    attitude = clean_value(row.get("attitude"))
    return {
        "source_id": source_id,
        "dataset": DATASET,
        "dialogue": parse_dialogue(row.get("dialogue")),
        "intake_form": {**parse_intake_form(row.get("intake_form")),
                        **parse_intake_sections(row.get("intake_form"))},
        "attitude": attitude.lower() if attitude else None,
        "thought": clean_value(row.get("thought")),
        "patterns": parse_patterns(row.get("patterns")),
        "reframed_thought": clean_value(row.get("reframed_thought")),
    }


def dialogue_fingerprint(record: dict) -> str:
    joined = "\n".join(f"{t['speaker']}:{t['text'].lower()}" for t in record["dialogue"])
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
