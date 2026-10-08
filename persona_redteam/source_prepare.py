"""Pinned VERA acquisition and source-faithful JMIR reconstruction, no inference.

The historical JMIR importer is absent from current main. Our explicit JSONL
schema/positional IDs preserve source inputs but are not claimed to recover its
wire format. A checksum mismatch is reported, never serialization-tuned.
Run: python -m persona_redteam.source_prepare --source-dir <ignored cache>
Sources must first be acquired from the immutable URLs in SOURCES. No network
calls happen in this module. Outputs stay in gitignored directories; no 652
client-classification or Cactus-ranking step is implemented.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path

SOURCES = {
    "vera_si.tsv": {
        "repository": "SpringCare/VERA-MH", "revision": "546e431f532389684f8b581a8ec1d83d86ad12d1",
        "path": "data/SI/personas.tsv",
        "sha256": "07f0aa92cde50469d18aff640ed03e0df93e8863aed75ea102e4ba97a124330b"},
    "jmir_test.json": {
        "repository": "ellisalicante/LLMs-Mental-Health-Crisis",
        "revision": "91032137b958bd4c69dbf703b91eb753a59909ba",
        "path": "data/processed/sampled_dataset_n_2046_nPerD168_seed0.json",
        "sha256": "a4cacb7f899b7d99e1acbfce995eafa6325735d47e19cb2f2f0c04063614b344"},
    "jmir_labels.json": {
        "repository": "ellisalicante/LLMs-Mental-Health-Crisis",
        "revision": "91032137b958bd4c69dbf703b91eb753a59909ba",
        "path": "data/llm_label/gpt-4o-mini-labeled-sampled_dataset_n_2046_nPerD168_seed0-merged-labels.json",
        "sha256": "ff1ade27018fb30a1d07377664778f4652c57a90d64641c3db4e260986e9fb6f"}}
SOURCE_HF = {
    "hugg_1": "sajjadhadi/Mental-Disorder-Detection-Data", "hugg_2": "marmikpandya/mental-health",
    "hugg_3": "fadodr/mental_health_dataset", "hugg_4": "fadodr/mental_health_therapy",
    "hugg_5": "psycode1/psyset", "hugg_6": "marmikpandya/mental-health",
    "hugg_7": "Amod/mental_health_counseling_conversations", "hugg_8": "cypsiSAS/transformed_Suicidal_ideation",
    "hugg_9": "fanyin3639/test_test_self_harm_all_levels", "hugg_10": "arianaazarbal/self-harm-synthetic-eval",
    "hugg_11": "richie-ghost/suicidal_finetune", "hugg_16k": "ShenLab/MentalChat16K",
    "hugg_100k": "jerryjalapeno/nart-100k-synthetic"}
# Mapping above comes from src/load_datasets.py at JMIR revision 91032137...
CRISIS_LABELS = {"suicidal_ideation", "anxiety_crisis", "substance_abuse_or_withdrawal",
                 "self-harm", "violent_thoughts", "risk_taking_behaviours"}
FULL_COUNTS = {"suicidal_ideation": 380, "no_crisis": 1231, "anxiety_crisis": 177,
               "substance_abuse_or_withdrawal": 77, "self-harm": 139,
               "violent_thoughts": 21, "risk_taking_behaviours": 19, "None": 2}
CRISIS_COUNTS = {k: v for k, v in FULL_COUNTS.items() if k not in ("None", "no_crisis")}
VERA_COUNTS = {"None": 10, "Low": 30, "High": 30, "Immediate": 30}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_source(directory, name):
    data = (Path(directory) / name).read_bytes()
    if digest(data) != SOURCES[name]["sha256"]:
        raise ValueError(f"pinned source hash mismatch: {name}")
    return data


def validate_vera(data):
    reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), delimiter="\t")
    rows = list(reader)
    required = {"Name", "Age", "Gender", "Background", "Short Current Suicide Risk Level",
                "Diagnoses and Symptoms", "Current Suicidal Thoughts and Behaviors",
                "Recent Triggers and Stressors", "Primary Communication Style", "Reaction to Chatbot Responses"}
    if not required.issubset(reader.fieldnames or []):
        raise ValueError("VERA missing required columns")
    if any(None in r or any(value is None for value in r.values()) for r in rows):
        raise ValueError("VERA malformed TSV row")
    risks = dict(Counter(r["Short Current Suicide Risk Level"] for r in rows))
    if len(rows) != 100 or risks != VERA_COUNTS or len({r["Name"] for r in rows}) != 100:
        raise ValueError("VERA counts/unique names do not match native SI pool")
    return {"rows": len(rows), "columns": reader.fieldnames, "risk_counts": risks,
            "unique_names": len({r["Name"] for r in rows}), "bytes": len(data), "sha256": digest(data)}


def reconstruct_jmir(test, labels):
    """Verified positional join, as in the authors' merge_labeled_datasets.py.

    dataset_id is a corpus ID, not a unique conversation ID. A local goal_id is
    explicitly derived from source-row position; original ordered inputs and
    dataset_id are retained. goal is a newline join without stripping/rewriting.
    This rendering/field order is ours, not recovered historical import code.
    """
    if not isinstance(test, list) or not isinstance(labels, list) or len(test) != len(labels):
        raise ValueError("JMIR source lists must have equal lengths")
    rows, seen = [], set()
    for index, (original, merged) in enumerate(zip(test, labels)):
        if not isinstance(original, dict) or not isinstance(merged, dict):
            raise ValueError(f"JMIR row {index}: expected objects")
        inputs = original.get("inputs")
        dataset = original.get("dataset_id")
        if not isinstance(inputs, list) or not inputs or not all(isinstance(s, str) for s in inputs):
            raise ValueError(f"JMIR row {index}: invalid inputs")
        if dataset not in SOURCE_HF:
            raise ValueError(f"JMIR row {index}: unknown dataset_id")
        if merged.get("dataset_id") != dataset or merged.get("inputs") != inputs:
            raise ValueError(f"JMIR row {index}: source/label positional alignment mismatch")
        if "label" not in merged:
            raise ValueError(f"JMIR row {index}: missing merged-label field")
        label = merged["label"]
        if label not in CRISIS_LABELS | {"no_crisis", None, ""}:
            raise ValueError(f"JMIR row {index}: unknown merged label")
        content_key = (dataset, tuple(inputs))
        if content_key in seen:
            raise ValueError("JMIR duplicate composite conversation key; do not silently merge")
        seen.add(content_key)
        rows.append({"goal_id": f"jmir-source-{index:04d}", "goal": "\n".join(inputs),
                     "crisis_label": label, "source_hf": SOURCE_HF[dataset], "dataset_id": dataset,
                     "source_row_index": index, "inputs": list(inputs),
                     "original_label": original.get("label")})
    return rows


def crisis_subset(rows):
    """Only remove no_crisis and missing labels; preserve rows/order/IDs unchanged."""
    return [row for row in rows if row["crisis_label"] not in ("no_crisis", None, "")]


def jsonl_bytes(rows):
    return ("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n").encode("utf-8") if rows else b""


def summarize(rows, data):
    ids = [r["goal_id"] for r in rows]
    return {"rows": len(rows), "unique_goal_ids": len(set(ids)),
            "crisis_label_counts": dict(Counter(str(r["crisis_label"]) for r in rows)),
            "source_dataset_counts": dict(Counter(r["dataset_id"] for r in rows)),
            "source_hf_counts": dict(Counter(r["source_hf"] for r in rows)),
            "bytes": len(data), "sha256": digest(data)}


def compare_manifest(actual, expected):
    fields = ("rows", "bytes", "sha256", "crisis_label_counts", "risk_counts")
    return {field: {"expected": expected[field], "actual": actual.get(field)}
            for field in fields if field in expected and actual.get(field) != expected[field]}


def write_once(path, data):
    path = Path(path)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"refusing to overwrite different content: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parent
    if root / "outputs" not in args.source_dir.resolve().parents:
        parser.error("source cache must stay under ignored persona_redteam/outputs/")
    targets = {f["path"]: f for f in json.loads((root / "DATA_MANIFEST.json").read_text())["files"]}
    vera_data = read_source(args.source_dir, "vera_si.tsv")
    vera = validate_vera(vera_data)
    vera_diff = compare_manifest(vera, targets["personas/veramh_si_n100.tsv"])
    if vera_diff:
        raise ValueError(f"VERA source mismatch: {vera_diff}")
    write_once(root / "personas/veramh_si_n100.tsv", vera_data)
    test = json.loads(read_source(args.source_dir, "jmir_test.json"))
    labels = json.loads(read_source(args.source_dir, "jmir_labels.json"))
    full = reconstruct_jmir(test, labels)
    subset = crisis_subset(full)
    summaries = {"2046": summarize(full, jsonl_bytes(full)), "813": summarize(subset, jsonl_bytes(subset))}
    if (len(full) != 2046 or summaries["2046"]["crisis_label_counts"] != FULL_COUNTS
            or len(subset) != 813 or summaries["813"]["crisis_label_counts"] != CRISIS_COUNTS):
        raise ValueError("JMIR source-grounded stage counts mismatch; stop")
    diffs = {n: compare_manifest(summaries[n], targets[f"goals/crisis_goals_jmir_n{n}.jsonl"])
             for n in ("2046", "813")}
    for n, rows in (("2046", full), ("813", subset)):
        # Nonmatching reconstructions never masquerade as canonical artifacts.
        destination = (root / f"goals/crisis_goals_jmir_n{n}.jsonl" if not diffs[n]
                       else args.source_dir / f"reconstructed_jmir_n{n}.jsonl")
        write_once(destination, jsonl_bytes(rows))
    report = {"sources": SOURCES, "vera": vera, "vera_manifest_differences": vera_diff,
              "jmir": summaries, "jmir_manifest_differences": diffs,
              "jmir_rendering_status": "explicit reconstruction, historical importer unavailable",
              "jmir_join": "position plus exact dataset_id/inputs validation; 2046 unique composite keys",
              "serialization": "UTF-8, ensure_ascii=False, insertion field order, LF and final LF",
              "unknown_historical_conventions": ["goal_id generation", "goal rendering", "additional fields",
                                                 "field ordering", "JSON serialization", "newline convention"],
              "blocked": ["historical JMIR import wire format", "813-to-652 retained classifier decisions",
                          "Cactus historical top-2000 artifact/ranking"]}
    write_once(args.source_dir / "validation_report.json", json.dumps(report, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if any(diffs.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
