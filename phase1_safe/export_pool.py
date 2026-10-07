"""Export phase1_safe personas to the persona_redteam Cactus pool row format.

DRAFT. Target: ``persona_redteam/personas/cactus_distress_n2000.jsonl`` on the
fork's ``main`` (README §3.2, rebuild plan §9 step 5). That file's producer is
not in the repo, so this exporter reimplements the row format from:

- the consumer contract (fields read by ``extract_persona_pathology.py``,
  ``match_pathology.py``, ``select_by_surrogate.py``, ``tests/synthetic_inputs.py``):
  ``persona_id`` must be a unique non-empty string; text fields are read with
  ``row.get(field, "")`` inside f-strings, so a JSON ``null`` would render as
  the text "None" -- text fields are therefore omitted, never written as null;
- the README field list: persona_id, descriptor, background, condition, thought,
  patterns, cognitive_distortion, style_reference, distress_tags, resistance.

How each field is filled is a *mapping spec* (JSON). Fields whose source is
not confirmed default to ``unresolved``: export fails unless
``on_unresolved="omit"`` (dry run), which leaves the key out and records it.
See docs/PHASE1_POOL_EXPORT.md for the evidence behind each candidate.

This module only formats source-derived persona data. It does not select the
final 2,000 rows (the README's distress ranking is unspecified) and does not
touch goals, prompts or any model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from . import io_utils
from .schema import SCHEMA_VERSION

EXPORT_VERSION = "redteam-pool-export-draft-v0"
POOL_FIELDS = ("persona_id", "descriptor", "background", "condition", "thought", "patterns",
               "cognitive_distortion", "style_reference", "distress_tags", "resistance")
TEXT_FIELDS = ("persona_id", "descriptor", "background", "condition", "thought",
               "cognitive_distortion", "style_reference")
LIST_FIELDS = ("patterns", "distress_tags")
STRATEGIES = ("copy", "join", "first_text", "join_texts", "legacy_descriptor",
              "legacy_cognitive_distortion", "unresolved")
ON_UNRESOLVED = ("fail", "omit")


class UnresolvedFieldError(ValueError):
    pass


def _get(ctx, path):
    """Resolve "record.intake_form.age" / "persona.style_references" in ctx."""
    cur = ctx
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(f"path {path!r}: missing {part!r}")
        cur = cur[part]
    return cur


def _texts(items):
    if not isinstance(items, list):
        raise TypeError("expected a list of {text: ...} items")
    return [i["text"] for i in items if isinstance(i, dict) and isinstance(i.get("text"), str) and i["text"]]


def legacy_descriptor(ctx):
    """Format of the archived build_personas.py ("a 41-year-old female Clerk"),
    except missing parts are dropped instead of defaulting occupation to "person"."""
    p = ctx["persona"]["persona"]
    parts = [f"{p['age']}-year-old" if p.get("age") else None, p.get("gender"), p.get("occupation")]
    parts = [x for x in parts if x]
    return f"a {' '.join(parts)}" if parts else None


def legacy_cognitive_distortion(ctx):
    """Format of the archived build_personas.py: "<first pattern>: <thought[:160]>"."""
    state = ctx["persona"]["psychological_state"]
    patterns, thought = state.get("patterns") or [], state.get("thought")
    if not patterns or not thought:
        return None
    return f"{patterns[0]}: {thought[:160]}"


def apply_field(spec, ctx):
    strategy = spec.get("strategy")
    if strategy == "copy":
        return _get(ctx, spec["path"])
    if strategy == "join":
        vals = [_get(ctx, p) for p in spec["paths"]]
        vals = [v for v in vals if isinstance(v, str) and v]
        return spec.get("sep", " ").join(vals) or None
    if strategy == "first_text":
        texts = _texts(_get(ctx, spec["path"]))
        return texts[0] if texts else None
    if strategy == "join_texts":
        return spec.get("sep", " ").join(_texts(_get(ctx, spec["path"]))) or None
    if strategy == "legacy_descriptor":
        return legacy_descriptor(ctx)
    if strategy == "legacy_cognitive_distortion":
        return legacy_cognitive_distortion(ctx)
    if strategy == "unresolved":
        raise UnresolvedFieldError(spec.get("todo", "unresolved"))
    raise ValueError(f"unknown strategy {strategy!r}; choose from {STRATEGIES}")


def validate_mapping(mapping) -> list[str]:
    errs = []
    fields = mapping.get("fields")
    if not isinstance(fields, dict):
        return ["mapping.fields: required object"]
    for f in POOL_FIELDS:
        if f not in fields:
            errs.append(f"mapping.fields.{f}: missing (use strategy 'unresolved' if unknown)")
    for f, spec in fields.items():
        if f not in POOL_FIELDS:
            errs.append(f"mapping.fields.{f}: not a pool field")
        elif not isinstance(spec, dict) or spec.get("strategy") not in STRATEGIES:
            errs.append(f"mapping.fields.{f}: strategy must be one of {STRATEGIES}")
    if fields.get("persona_id", {}).get("strategy") == "unresolved":
        errs.append("mapping.fields.persona_id: cannot be unresolved")
    return errs


def export_rows(records, personas, mapping, on_unresolved="fail"):
    """Return (rows, provenance). Joins record and persona on source_id."""
    if on_unresolved not in ON_UNRESOLVED:
        raise ValueError(f"on_unresolved must be one of {ON_UNRESOLVED}")
    errs = validate_mapping(mapping)
    if errs:
        raise ValueError("; ".join(errs))
    by_source = {}
    for r in records:
        if r["source_id"] in by_source:
            raise ValueError(f"duplicate record source_id {r['source_id']}")
        by_source[r["source_id"]] = r
    unresolved = sorted(f for f, s in mapping["fields"].items() if s["strategy"] == "unresolved")
    if unresolved and on_unresolved == "fail":
        raise UnresolvedFieldError(f"unresolved fields: {unresolved} (resolve them in the mapping, "
                                   "or use on_unresolved='omit' for a dry run)")
    rows, provenance = [], []
    for persona in personas:
        record = by_source.get(persona["source_id"])
        if record is None:
            raise ValueError(f"no record for persona source_id {persona['source_id']}")
        ctx = {"record": record, "persona": persona}
        row, omitted = {}, {}
        for field in POOL_FIELDS:
            spec = mapping["fields"][field]
            if spec["strategy"] == "unresolved":
                omitted[field] = "unresolved"
                continue
            value = apply_field(spec, ctx)
            if value is None or (field in LIST_FIELDS and value == []):
                omitted[field] = "source_missing"
                continue
            row[field] = value
        rows.append(row)
        provenance.append({
            "persona_id": row["persona_id"], "source_id": persona["source_id"],
            "dataset": persona["dataset"], "phase1_persona_id": persona["persona_id"],
            "schema_version": persona.get("schema_version", SCHEMA_VERSION),
            "adapter_version": persona["provenance"].get("adapter_version"),
            "selection_rule": persona["provenance"].get("selection_rule"),
            "seed": persona["provenance"].get("seed"),
            "mapping_id": mapping.get("mapping_id"), "export_version": EXPORT_VERSION,
            "omitted_fields": omitted,
        })
    return rows, provenance


def validate_pool_rows(rows, expected_rows=None) -> list[str]:
    """Consumer contract of persona_redteam's Cactus pool loaders."""
    errs, seen = [], set()
    if expected_rows is not None and len(rows) != expected_rows:
        errs.append(f"expected {expected_rows} rows, got {len(rows)}")
    for i, row in enumerate(rows):
        pid = row.get("persona_id")
        if not isinstance(pid, str) or not pid.strip():
            errs.append(f"row {i}: persona_id must be a non-empty string")
        elif pid in seen:
            errs.append(f"row {i}: duplicate persona_id {pid!r}")
        else:
            seen.add(pid)
        for f in TEXT_FIELDS:
            if f in row and not isinstance(row[f], str):
                errs.append(f"row {i}: {f} must be a string or absent (null renders as 'None')")
        for f in LIST_FIELDS:
            if f in row and not (isinstance(row[f], list) and all(isinstance(x, str) for x in row[f])):
                errs.append(f"row {i}: {f} must be a list of strings or absent")
    return errs


def compare_with_manifest(pool_path, manifest_path, entry_path="personas/cactus_distress_n2000.jsonl"):
    """Compare an exported file with a DATA_MANIFEST.json entry (rows, bytes, sha256)."""
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    entry = next((f for f in manifest.get("files", []) if f.get("path") == entry_path), None)
    if entry is None:
        raise ValueError(f"{entry_path} not in {manifest_path}")
    data = Path(pool_path).read_bytes()
    actual = {"rows": sum(1 for line in data.splitlines() if line.strip()), "bytes": len(data),
              "sha256": hashlib.sha256(data).hexdigest()}
    return {"entry": entry_path,
            **{k: {"expected": entry.get(k), "actual": actual[k], "match": entry.get(k) == actual[k]}
               for k in ("rows", "bytes", "sha256")}}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="phase1_safe.export_pool")
    ap.add_argument("--records", type=Path, required=True, help="records.jsonl from `run build`")
    ap.add_argument("--personas", type=Path, required=True, help="personas.jsonl from `run build`")
    ap.add_argument("--mapping", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="pool JSONL to write")
    ap.add_argument("--on-unresolved", choices=ON_UNRESOLVED, default="fail")
    ap.add_argument("--expected-rows", type=int, default=None)
    ap.add_argument("--compare-manifest", type=Path, default=None,
                    help="persona_redteam/DATA_MANIFEST.json to compare rows/bytes/sha256 against")
    args = ap.parse_args(argv)
    mapping = json.loads(args.mapping.read_text(encoding="utf-8"))
    try:
        rows, provenance = export_rows(io_utils.load_rows(args.records), io_utils.load_rows(args.personas),
                                       mapping, args.on_unresolved)
    except UnresolvedFieldError as exc:
        print(f"[abort] {exc}", file=sys.stderr)
        return 2
    errors = validate_pool_rows(rows, args.expected_rows)
    if errors:
        for e in errors[:20]:
            print(f"[invalid] {e}", file=sys.stderr)
        return 3
    io_utils.write_jsonl(args.out, rows)
    prov_path = args.out.with_name(args.out.stem + ".provenance.jsonl")
    io_utils.write_jsonl(prov_path, provenance)
    report = {
        "export_version": EXPORT_VERSION, "mapping_id": mapping.get("mapping_id"),
        "mapping_sha256": io_utils.sha256_file(args.mapping), "on_unresolved": args.on_unresolved,
        "inputs": {"records": {"path": str(args.records), "sha256": io_utils.sha256_file(args.records)},
                   "personas": {"path": str(args.personas), "sha256": io_utils.sha256_file(args.personas)}},
        "rows": len(rows), "output_sha256": io_utils.sha256_file(args.out),
        "fields_present": {f: sum(1 for r in rows if f in r) for f in POOL_FIELDS},
        "status": "DRAFT dry run" if args.on_unresolved == "omit" else "draft export",
    }
    if args.compare_manifest:
        report["manifest_comparison"] = compare_with_manifest(args.out, args.compare_manifest)
    io_utils.write_json(args.out.with_name(args.out.stem + ".export_manifest.json"), report)
    print(f"[export] {len(rows)} rows -> {args.out} (+ provenance, export manifest)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
