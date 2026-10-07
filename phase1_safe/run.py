"""CLI for the Phase 1 safe pipeline.

    python3 -m phase1_safe.run profile --input data/raw/cactus.json --out-dir runs/phase1_safe/profile
    python3 -m phase1_safe.run build   --input data/raw/cactus.json --out-dir runs/phase1_safe/build \\
        --n 150 --seed 0 [--style-k 3] [--resistance lexical-v1] [--bindings bindings.jsonl]

Outputs (build): records.jsonl (selected canonical records), personas.jsonl,
specs.jsonl, manifest.json. Outputs are byte-identical for the same input and
arguments; only manifest.json carries a timestamp.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import io_utils
from .adapters import cactus
from .bind import apply_bindings
from .compile_spec import SPEC_VERSION, compile_spec
from .extract import RESISTANCE_METHODS, build_persona
from .profile import profile_records
from .schema import ADAPTER_VERSION, SCHEMA_VERSION, validate_persona, validate_record
from .select_records import describe_rule, sample_records, select_records

FORMATS = ("cactus", "canonical")


def load_records(path, fmt):
    rows = io_utils.load_rows(path)
    if fmt == "canonical":
        records = rows
    else:
        records = [cactus.to_record(r, i) for i, r in enumerate(rows)]
    bad = [(r.get("source_id"), e) for r in records for e in validate_record(r)]
    return records, bad


def cmd_profile(args):
    records, bad = load_records(args.input, args.format)
    report = profile_records(records, parse_errors=len(bad))
    report["input"] = {"path": str(args.input), "sha256": io_utils.sha256_file(args.input), "format": args.format}
    io_utils.write_json(Path(args.out_dir) / "profile.json", report)
    print(f"[profile] {report['records']} records, {report['negative_records']} negative -> {args.out_dir}/profile.json")
    return 0


def cmd_build(args):
    records, bad = load_records(args.input, args.format)
    if bad:
        for sid, e in bad[:20]:
            print(f"[invalid] {sid}: {e}", file=sys.stderr)
        print(f"[abort] {len(bad)} schema errors in input records", file=sys.stderr)
        return 2
    attitudes = tuple(a for a in args.attitudes.split(",") if a) if args.attitudes else ()
    kept, stats = select_records(records, attitudes=attitudes, require_thought=not args.allow_missing_thought,
                                 require_patterns=not args.allow_missing_patterns,
                                 dedup_client=not args.keep_all_client_dialogues, min_age=args.min_age)
    picked = sample_records(kept, args.n, args.seed)
    rule = describe_rule(attitudes, not args.allow_missing_thought, not args.allow_missing_patterns,
                         not args.keep_all_client_dialogues, args.min_age)
    personas = [build_persona(r, seed=args.seed, selection_rule=rule, style_k=args.style_k,
                              style_min_chars=args.style_min_chars, style_max_chars=args.style_max_chars,
                              resistance_method=args.resistance) for r in picked]
    binding_stats = None
    if args.bindings:
        binding_stats = apply_bindings(personas, io_utils.load_rows(args.bindings))
    errors = [(p["persona_id"], e) for p in personas for e in validate_persona(p)]
    if errors:
        for pid, e in errors[:20]:
            print(f"[invalid persona] {pid}: {e}", file=sys.stderr)
        return 3
    out = Path(args.out_dir)
    io_utils.write_jsonl(out / "records.jsonl", picked)
    io_utils.write_jsonl(out / "personas.jsonl", personas)
    io_utils.write_jsonl(out / "specs.jsonl", [compile_spec(p) for p in personas])
    io_utils.write_json(out / "manifest.json", {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": SCHEMA_VERSION, "adapter_version": ADAPTER_VERSION, "spec_version": SPEC_VERSION,
        "input": {"path": str(args.input), "sha256": io_utils.sha256_file(args.input), "format": args.format},
        "bindings": {"path": str(args.bindings), "sha256": io_utils.sha256_file(args.bindings), **binding_stats}
        if args.bindings else None,
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items() if k != "func"},
        "selection_rule": rule,
        "filter_stats": stats,
        "sampled": len(picked),
        "resistance_status_counts": {s: sum(1 for p in personas if p["resistance"]["status"] == s)
                                     for s in ("observed", "not_observed", "unknown")},
        "persona_field_coverage": {f: sum(1 for p in personas if p["persona"][f]) for f in personas[0]["persona"]}
        if personas else {},
        "status": "implementation pilot (not a Table 6 reproduction)",
    })
    print(f"[build] {stats['total']} records -> {stats['kept']} kept -> {len(picked)} personas -> {out}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="phase1_safe")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("profile", "build"):
        p = sub.add_parser(name)
        p.add_argument("--input", type=Path, required=True)
        p.add_argument("--format", choices=FORMATS, default="cactus")
        p.add_argument("--out-dir", type=Path, required=True)
    b = sub.choices["build"]
    b.add_argument("--n", type=int, default=None, help="personas to sample (default: all selected)")
    b.add_argument("--seed", type=int, default=0)
    b.add_argument("--attitudes", default="negative", help="comma list; empty string = any (provisional)")
    b.add_argument("--allow-missing-thought", action="store_true")
    b.add_argument("--allow-missing-patterns", action="store_true")
    b.add_argument("--keep-all-client-dialogues", action="store_true",
                   help="do not collapse multiple dialogues of the same client")
    b.add_argument("--min-age", type=int, default=None,
                   help="drop clients younger than this or without a numeric age (team decision; default off)")
    b.add_argument("--style-k", type=int, default=3, help="provisional default")
    b.add_argument("--style-min-chars", type=int, default=20)
    b.add_argument("--style-max-chars", type=int, default=400)
    b.add_argument("--resistance", choices=RESISTANCE_METHODS, default="none")
    b.add_argument("--bindings", type=Path, default=None)
    args = ap.parse_args(argv)
    return cmd_profile(args) if args.cmd == "profile" else cmd_build(args)


if __name__ == "__main__":
    sys.exit(main())
