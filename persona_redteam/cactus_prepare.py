"""Offline Cactus preprocessing; historical distress ranking remains unresolved.

Run from the repository root: python -m persona_redteam.cactus_prepare prepare
--raw <pinned cactus.json> [--out <candidate JSONL under persona_redteam/outputs>].
The optional output is the unranked candidate pool, never the historical 2,000.
validate-artifact --raw ... --artifact ... audits a future historical JSONL.
Only standard-library code is used; no model calls or clinical labels are added.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

RAW_SHA256 = "be3421495f9dd76dd47d5fd4abd9fdabed9c97fcb7f7bba34ecfc78fe07d3d18"
RAW_ROWS = 31577
ATTITUDES = {"negative": 9469, "neutral": 10882, "positive": 11226}
HISTORICAL = {"sha256": "09796d4c70cbd8567955ec9d29096843ded565e7a89718b231e393f6d229ea80",
              "bytes": 2550191, "rows": 2000}
FIELDS = ("thought", "patterns", "intake_form", "dialogue", "attitude", "cbt_technique", "cbt_plan")
PERSONA_FIELDS = ("persona_id", "descriptor", "background", "condition", "thought", "patterns",
                  "cognitive_distortion", "style_reference", "distress_tags", "resistance")
PLACEHOLDERS = {"", "-", "n/a", "na", "none specified", "not specified", "unspecified",
                "undisclosed", "unknown", "not provided", "not mentioned", "not applicable"}
SPEAKERS = {"client": "client", "patient": "client", "counselor": "counselor",
            "counsellor": "counselor", "therapist": "counselor"}
SPEAKER_RE = re.compile(r"^\s*(client|patient|counsel+or|therapist)\s*(\([^()\r\n]*\))?\s*:\s*(.*)$", re.I)


def normalize_thought(text):
    """Collapse whitespace only; preserve case, punctuation and source thought.

    Raw exact-string uniqueness is already 4,011 on the pinned corpus. This rule
    does not recover the undocumented historical normalization or ranking.
    """
    return " ".join(text.split())


def clean_value(text):
    if text is None:
        return None
    text = " ".join(text.split())
    return None if text.lower().rstrip(".") in PLACEHOLDERS else text


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_schema(rows):
    if not isinstance(rows, list):
        raise ValueError("raw input must be a JSON list")
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {index}: expected object")
        for field in FIELDS:
            value = row.get(field)
            valid = (isinstance(value, list) and all(isinstance(p, str) for p in value)
                     if field == "patterns" else isinstance(value, str))
            if not valid:
                raise ValueError(f"row {index}: invalid or missing {field}")
        if row["attitude"] not in ATTITUDES:
            raise ValueError(f"row {index}: unsupported attitude")
        if not normalize_thought(row["thought"]):
            raise ValueError(f"row {index}: empty thought")


def load_pinned_raw(path):
    actual = sha256(path)
    if actual != RAW_SHA256:
        raise ValueError(f"raw SHA256 mismatch: {actual}")
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_schema(rows)
    if len(rows) != RAW_ROWS or dict(Counter(r["attitude"] for r in rows)) != ATTITUDES:
        raise ValueError("pinned raw stage counts mismatch")
    return rows


def parse_dialogue(text):
    """Minimal audited speaker parser; qualifiers remain literal utterance text."""
    turns = []
    for line in text.splitlines():
        match = SPEAKER_RE.match(line)
        if match:
            body = " ".join(p.strip() for p in (match[2], match[3]) if p and p.strip())
            turns.append({"speaker": SPEAKERS.get(match[1].lower(), "counselor"), "text": body})
        elif turns and line.strip():
            turns[-1]["text"] += " " + line.strip()
    turns = [t for t in turns if t["text"].strip()]
    for index, turn in enumerate(turns):
        turn.update(turn_id=index, text=" ".join(turn["text"].split()))
    return turns


def intake_fields(text):
    """Read explicit demographic labels and numbered sections; invent no defaults."""
    result = dict.fromkeys(("name", "age", "gender", "occupation"))
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(name|age|gender|occupation)\s*:\s*(.*)$", line, re.I)
        if match and result[match[1].lower()] is None:
            value = match[2].strip()
            if not value:
                value = next((s.strip() for s in lines[index + 1:] if s.strip()), "")
                if ":" in value or re.match(r"^\d+[.)]", value):
                    value = ""
            result[match[1].lower()] = clean_value(value)
    sections = {}
    active = None
    for line in lines:
        heading = re.match(r"^\s*\d+[.)]\s*(.+)$", line)
        if heading:
            active = heading[1].strip().rstrip(":").lower()
            sections[active] = []
        elif active:
            sections[active].append(line)
    result["presenting_problem"] = clean_value(" ".join(sections.get("presenting problem", [])))
    result["reason_for_seeking_help"] = next(
        (clean_value(" ".join(body)) for heading, body in sections.items()
         if heading.startswith("reason for seeking")), None)
    return result


def extract_candidate(row, index):
    intake = intake_fields(row["intake_form"])
    turns = parse_dialogue(row["dialogue"])
    sid = f"cactus-{index:06d}"
    # These are transparent source renderings, not recovered historical wording.
    descriptor = "; ".join(f"{key}: {intake[key]}" for key in ("age", "gender", "occupation")
                           if intake[key] is not None) or None
    first_client = next((t for t in turns if t["speaker"] == "client"), None)
    return {"persona_id": f"candidate-{sid}", "source_id": sid, "source_row_index": index,
            "source": "Cactus", "normalized_thought": normalize_thought(row["thought"]),
            "descriptor": descriptor, "background": row["intake_form"],
            "condition": intake["presenting_problem"], "thought": row["thought"],
            "patterns": list(row["patterns"]),
            "cognitive_distortion": "; ".join(row["patterns"]) or None,
            "style_reference": first_client["text"] if first_client else None,
            "style_reference_turn_id": first_client["turn_id"] if first_client else None,
            "intake": intake, "dialogue": turns,
            "distress_tags": None, "resistance": None,
            "unresolved_fields": ["historical_persona_id", "historical_field_rendering",
                                  "distress_tags", "resistance", "distress_ranking"],
            "provenance": {"representative_rule": "first negative row in raw order",
                           "normalization": "whitespace-only-v1",
                           "candidate_schema_version": "cactus-candidate-v1",
                           "historical_representative_rule": "unknown"}}


def prepare_candidates(rows):
    validate_schema(rows)
    candidates, by_thought = [], {}
    negative = 0
    for index, row in enumerate(rows):
        if row["attitude"] != "negative":
            continue
        negative += 1
        key = normalize_thought(row["thought"])
        if key not in by_thought:
            candidate = extract_candidate(row, index)
            candidate["duplicate_source_row_indices"] = []
            by_thought[key] = candidate
            candidates.append(candidate)
        by_thought[key]["duplicate_source_row_indices"].append(index)
    return candidates, {"raw_rows": len(rows), "attitudes": dict(Counter(r["attitude"] for r in rows)),
                        "negative_rows": negative, "exact_unique_negative_thoughts": len({
                            r["thought"] for r in rows if r["attitude"] == "negative"}),
                        "normalized_unique_thoughts": len(candidates),
                        "duplicate_negative_rows": negative - len(candidates),
                        "ranking_status": "unresolved; production stops at candidate pool"}


def validate_artifact(path, rows, expected=HISTORICAL):
    """Audit membership, source ambiguity and literal field fidelity without ranking.

    Thought membership does not establish byte identity or historical selection.
    An unresolved field is reported even when the artifact hash is authentic.
    """
    path = Path(path)
    if not path.exists():
        return {"status": "missing", "path": str(path), "expected": expected}
    candidates, _ = prepare_candidates(rows)
    pool = {c["normalized_thought"]: c for c in candidates}
    artifact = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not all(isinstance(r, dict) for r in artifact):
        raise ValueError("historical JSONL rows must be objects")
    ids = [r.get("persona_id") for r in artifact]
    schema = defaultdict(Counter)
    mappings = []
    for index, row in enumerate(artifact):
        for field, value in row.items():
            schema[field][type(value).__name__] += 1
        thought = row.get("thought")
        key = normalize_thought(thought) if isinstance(thought, str) else None
        candidate = pool.get(key)
        source_indices = candidate["duplicate_source_row_indices"] if candidate else []
        options = [extract_candidate(rows[i], i) for i in source_indices]
        supported = {field: [o["source_row_index"] for o in options if field in o and o[field] == value]
                     for field, value in row.items() if field not in ("persona_id", "distress_tags", "resistance")}
        explicit = row.get("source_row_index")
        if explicit is None and isinstance(row.get("source_id"), str):
            match = re.fullmatch(r"cactus-(\d+)", row["source_id"])
            explicit = int(match[1]) if match else None
        exact = set(source_indices)
        for field, matches in supported.items():
            if matches:
                exact.intersection_update(matches)
        if explicit is not None:
            exact.intersection_update([explicit])
        unmapped = [field for field in row if field in ("persona_id", "distress_tags", "resistance")
                    or not supported.get(field)]
        mappings.append({"row": index, "persona_id": row.get("persona_id"), "in_candidate_pool": candidate is not None,
                         "normalized_thought": key, "possible_source_row_indices": source_indices,
                         "jointly_supported_source_row_indices": sorted(exact),
                         "selected_source_row_id": f"cactus-{next(iter(exact)):06d}" if len(exact) == 1 else None,
                         "unmapped_fields": unmapped,
                         "missing_schema_fields": [f for f in PERSONA_FIELDS if f not in row]})
    actual = {"sha256": sha256(path), "bytes": path.stat().st_size, "rows": len(artifact)}
    valid_ids = [i for i in ids if isinstance(i, str) and i]
    return {"status": "inspected", **actual, "expected": expected,
            "integrity_matches": {k: actual[k] == v for k, v in expected.items()},
            "unique_persona_ids": len(set(valid_ids)), "invalid_persona_ids": len(ids) - len(valid_ids),
            "duplicate_persona_ids": len(valid_ids) - len(set(valid_ids)),
            "schema": {k: dict(v) for k, v in sorted(schema.items())},
            "every_row_in_candidate_pool": all(m["in_candidate_pool"] for m in mappings),
            "selected_raw_thought_order": [r.get("thought") for r in artifact],
            "selected_thought_order": [m["normalized_thought"] for m in mappings],
            "selected_thought_set": sorted({m["normalized_thought"] for m in mappings if m["normalized_thought"] is not None}),
            "mapping": mappings, "ranking_status": "historical rule unknown; no inferred ranking"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--raw", type=Path, required=True)
    prep.add_argument("--out", type=Path)
    check = sub.add_parser("validate-artifact")
    check.add_argument("--raw", type=Path, required=True)
    check.add_argument("--artifact", type=Path, required=True)
    args = parser.parse_args(argv)
    rows = load_pinned_raw(args.raw)
    if args.command == "prepare":
        candidates, report = prepare_candidates(rows)
        if len(candidates) != 4011:
            raise ValueError("pinned normalized-thought pool count mismatch")
        report.update(raw_sha256=sha256(args.raw), schema=list(candidates[0]))
        if args.out:
            allowed = Path(__file__).resolve().parent / "outputs"
            if allowed not in args.out.resolve().parents:
                parser.error("candidate outputs must stay under gitignored persona_redteam/outputs/")
            args.out.parent.mkdir(parents=True, exist_ok=True)
            with args.out.open("x", encoding="utf-8") as stream:
                for candidate in candidates:
                    stream.write(json.dumps(candidate, ensure_ascii=False, sort_keys=True) + "\n")
    else:
        report = validate_artifact(args.artifact, rows)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    if args.command == "validate-artifact":
        return 0 if (report["status"] == "inspected" and all(report["integrity_matches"].values())
                     and report["every_row_in_candidate_pool"] and not report["invalid_persona_ids"]
                     and not report["duplicate_persona_ids"]) else 1
    return 0


if __name__ == "__main__":
    main()
