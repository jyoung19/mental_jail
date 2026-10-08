"""Prepare, plan and run the public-code Phase-I reconstruction.

Preparation/planning is offline. Only `run --execute` permits model requests.
This uses the full 4,011 candidate pool, not the unavailable historical 2,000.
It makes new client-filter decisions, never claims to recover historical 652.
Research payloads and request receipts must stay under persona_redteam/outputs.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import fcntl
import getpass
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import urllib.request
import warnings

from . import cactus_prepare as cactus
from . import source_prepare as source
from .extraction.extract_goal_pathology import SYS as PATHOLOGY_SYSTEM
from .goals.filter_client_utterances import SYS as CLIENT_SYSTEM
from .matching.match_pathology import pool_texts, pathtext, rank_candidates
from .phase1_builder import UPSTREAM_COMMIT, UPSTREAM_SOURCE_SHA256
from .phase1_source_contract import (CONTRACT_VERSION, assemble_build, build_contract,
                                     build_locked_messages, lock_source)

ROOT = Path(__file__).resolve().parent
MODE = "public-code-reconstruction-cactus4011-jmir813-source-lock-v2"
MODELS = {"client_filter": "gpt-4o-mini", "pathology": "gpt-4o-mini",
          "embedding": "text-embedding-3-small", "builder": "gpt-4o-mini-2024-07-18"}
# USD per million standard text tokens, official model pages checked 2026-10-08.
# https://developers.openai.com/api/docs/models/gpt-4o-mini
# https://developers.openai.com/api/docs/models/text-embedding-3-small
PRICES = {"chat_input": 0.15, "chat_output": 0.60, "embedding_input": 0.02}
CODE_FILES = ("phase1_reproduce.py", "phase1_builder.py", "phase1_source_contract.py", "cactus_prepare.py", "source_prepare.py",
              "goals/filter_client_utterances.py", "extraction/extract_goal_pathology.py",
              "matching/match_pathology.py")


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    source.write_once(path, (json.dumps(value, ensure_ascii=False, indent=2,
                                       allow_nan=False) + "\n").encode())


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def run_directory(path):
    path = Path(path).resolve()
    if ROOT / "outputs" not in path.parents:
        raise ValueError("run directory must be a child of persona_redteam/outputs")
    protect_old_pilot(path)
    return path


def protect_old_pilot(path):
    protected = ROOT / "outputs/phase1_public_pilot12_approved"
    path = Path(path).resolve()
    if path == protected.resolve() or protected.resolve() in path.parents:
        raise ValueError("old pilot is immutable; use a NEW run directory")


def select_pilot(goals, per_label):
    """First N per label in source order, as upstream load_inputs; 0 selects all."""
    if per_label < 0:
        raise ValueError("per-label must be nonnegative")
    counts, chosen = Counter(), []
    ids = set()
    for row in goals:
        label, gid = row["crisis_label"], row["goal_id"]
        if label not in source.CRISIS_LABELS or not isinstance(gid, str) or gid in ids:
            raise ValueError("invalid crisis label or duplicate goal ID")
        ids.add(gid)
        if per_label == 0 or counts[label] < per_label:
            chosen.append(row)
            counts[label] += 1
    return chosen


def prepare(raw, source_dir, destination, per_label=2):
    destination = run_directory(destination)
    if destination.exists():
        raise ValueError("use a new run directory; preparation never overwrites a run")
    rows = cactus.load_pinned_raw(raw)
    candidates, stages = cactus.prepare_candidates(rows)
    vera_data = source.read_source(source_dir, "vera_si.tsv")
    vera_summary = source.validate_vera(vera_data)
    full = source.reconstruct_jmir(json.loads(source.read_source(source_dir, "jmir_test.json")),
                                   json.loads(source.read_source(source_dir, "jmir_labels.json")))
    crisis = source.crisis_subset(full)
    full_counts = dict(Counter(str(r["crisis_label"]) for r in full))
    if full_counts != source.FULL_COUNTS or len(crisis) != 813 or len(candidates) != 4011:
        raise ValueError("verified source-stage counts changed")
    goals = select_pilot(crisis, per_label)
    payloads = {"cactus_candidates.jsonl": source.jsonl_bytes(candidates),
                "vera.tsv": vera_data, "crisis_source.jsonl": source.jsonl_bytes(crisis),
                "pilot_goals.jsonl": source.jsonl_bytes(goals)}
    metadata = {name: {"sha256": source.digest(data), "bytes": len(data)} for name, data in payloads.items()}
    manifest = {"mode": MODE, "source_contract": CONTRACT_VERSION, "historical_artifact_reproduction": False,
                "paper_dataset_reproduction": False, "models": MODELS, "prices_per_million": PRICES,
                "upstream": {"main": "bdc8dd9e031c84f3c6c72fd60c2093f8aa8b53be",
                             "builder_commit": UPSTREAM_COMMIT,
                             "builder_source_sha256": UPSTREAM_SOURCE_SHA256},
                "code_sha256": {name: cactus.sha256(ROOT / name) for name in CODE_FILES},
                "inputs": {"cactus": {"sha256": cactus.RAW_SHA256, "rows": cactus.RAW_ROWS},
                           "official_sources": source.SOURCES},
                "counts": {"cactus": stages, "vera": vera_summary, "jmir_full": len(full),
                           "jmir_crisis": len(crisis), "pilot": len(goals),
                           "pilot_labels": dict(Counter(g["crisis_label"] for g in goals))},
                "selection": {"per_label": per_label, "rule": "first per label in original source order",
                              "topk": 3, "final_persona": "first retrieved candidate; incompatible selections blocked without substitution",
                              "client_filter_stage": "new decisions after pilot selection; not historical 652"},
                "limitations": ["Cactus 4011 is not historical ranked 2000",
                                "JMIR reconstructed wire format and local IDs differ from historical artifacts",
                                "new model outputs are not historical retained decisions",
                                "resistance/distress_tags remain unresolved; no clinical-history invention mode",
                                "paper CBT-DP, Cheeseburger Therapy and curated targets are not reproduced"],
                "payloads": metadata}
    for name, data in payloads.items():
        source.write_once(destination / name, data)
    write_json(destination / "manifest.json", manifest)
    return plan(destination)


def load_run(directory):
    directory = run_directory(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if manifest.get("mode") != MODE or manifest.get("models") != MODELS:
        raise ValueError("unsupported mode/model configuration")
    for name, expected in manifest["payloads"].items():
        path = directory / name
        if path.resolve().parent != directory or cactus.sha256(path) != expected["sha256"]:
            raise ValueError("run input hash mismatch: " + name)
    for name in CODE_FILES:
        if cactus.sha256(ROOT / name) != manifest["code_sha256"].get(name):
            raise ValueError("code changed since preparation; create a new run: " + name)
    return manifest


def plan(directory):
    manifest = load_run(directory)
    count = manifest["counts"]["pilot"]
    pool_counts = [manifest["counts"]["vera"]["rows"],
                   manifest["counts"]["cactus"]["normalized_unique_thoughts"]]
    embeddings = sum(math.ceil(n / 256) for n in [*pool_counts, count]) if count else 0
    vrows = list(csv.DictReader(io.StringIO((Path(directory) / "vera.tsv").read_text()), delimiter="\t"))
    crows = read_jsonl(Path(directory) / "cactus_candidates.jsonl")
    vt, ct = pool_texts(vrows, crows)
    return {"mode": MODE, "status": "prepared; inference requires approval and --execute",
            "models": MODELS, "pilot_goals": count, "pool_sizes": pool_counts,
            "maximum_requests": {"client_filter": count, "pathology": count,
                                 "embeddings": embeddings, "builder": count,
                                 "total": count * 3 + embeddings},
            "maximum_completion_tokens": count * (30 + 220 + 900),
            "pool_embedding_utf8_bytes": sum(len(t.encode()) for t in vt + ct),
            "goal_ids": [r["goal_id"] for r in read_jsonl(Path(directory) / "pilot_goals.jsonl")],
            "gpu_required": False, "historical_reproduction": False}


def request_cost_reserve(operation, body):
    """Conservative byte-based input estimate plus maximum output, not a bill.

    Avoids downloading tokenizers. Billing comes from API usage. The reserve
    includes margin for chat framing and does not assume cached-input discounts.
    """
    if operation == "embeddings":
        input_bound = sum(len(t.encode()) + 16 for t in body.get("input", []))
        return input_bound * PRICES["embedding_input"] / 1_000_000
    input_bound = len(json.dumps(body.get("messages", []), ensure_ascii=False).encode()) + 512
    return (input_bound * PRICES["chat_input"] + body.get("max_tokens", 0) * PRICES["chat_output"]) / 1_000_000


class RequestCache:
    """Checkpoint every request before sending; uncertain requests are not retried.

    Cache identity includes run fingerprint, stage, operation and exact body.
    A caller must hold the run lock. No API key is ever written to disk.
    """
    def __init__(self, directory, fingerprint, transport=None, max_requests=0, max_cost_usd=math.inf):
        self.directory = Path(directory) / "requests"
        self.fingerprint, self.transport = fingerprint, transport
        self.limit, self.sent = max_requests, 0
        self.max_cost = max_cost_usd
        previous = [json.loads(p.read_text()) for p in self.directory.glob("*.request.json")]
        self.previous_attempts = len(previous)
        self.reserved_cost = sum(request_cost_reserve(r["operation"], r["body"]) for r in previous)

    def request(self, stage, operation, body):
        identity = {"run": self.fingerprint, "stage": stage, "operation": operation, "body": body}
        key = digest(identity)
        attempt = self.directory / (key + ".request.json")
        result = self.directory / (key + ".response.json")
        if result.exists():
            cached = json.loads(result.read_text())
            if not attempt.exists() or json.loads(attempt.read_text()) != identity or cached.get("request_sha256") != key:
                raise ValueError("invalid request cache provenance")
            if cached.get("response_sha256") != digest(cached["response"]):
                raise ValueError("cached response hash mismatch")
            return cached["response"]
        if attempt.exists():
            raise RuntimeError("uncertain prior request; inspect before retrying: " + key)
        if self.transport is None:
            raise RuntimeError("inference is disabled")
        privacy_check(body.get("input", []) if operation == "embeddings" else
                      [m["content"] for m in body.get("messages", [])])
        if self.previous_attempts + self.sent >= self.limit:
            raise RuntimeError("approved request budget reached")
        reserve = request_cost_reserve(operation, body)
        if self.reserved_cost + reserve > self.max_cost:
            raise RuntimeError("approved estimated cost budget reached")
        write_json(attempt, identity)
        self.sent += 1
        self.reserved_cost += reserve
        try:
            response = self.transport(operation, body)
        except Exception as error:
            write_json(self.directory / (key + ".status.json"),
                       {"stage": stage, "status": "failed_or_uncertain", "error_type": type(error).__name__})
            raise RuntimeError("API request failed or is uncertain; no automatic retry") from None
        write_json(result, {"request_sha256": key, "response_sha256": digest(response), "response": response})
        write_json(self.directory / (key + ".status.json"), {"stage": stage, "status": "response_received"})
        return response

    def chat(self, stage, messages, max_tokens):
        body = {"model": MODELS[stage], "messages": messages, "temperature": 0,
                "max_tokens": max_tokens, "response_format": {"type": "json_object"}}
        response = self.request(stage, "chat/completions", body)
        choice = response["choices"][0]
        if choice.get("finish_reason") != "stop" or choice["message"].get("refusal"):
            raise ValueError("refused or truncated " + stage + " output; inspect cached response")
        value = json.loads(choice["message"]["content"])
        if not isinstance(value, dict):
            raise ValueError("expected JSON object from " + stage)
        return value

    def embed(self, texts):
        vectors = []
        for start in range(0, len(texts), 256):
            batch = texts[start:start + 256]
            response = self.request("embedding", "embeddings", {"model": MODELS["embedding"], "input": batch})
            data = sorted(response["data"], key=lambda row: row["index"])
            if [row["index"] for row in data] != list(range(len(batch))):
                raise ValueError("embedding response indices/count do not match request")
            vectors.extend(row["embedding"] for row in data)
        return vectors


PRIVATE_PATTERNS = {
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
    "phone": r"(?<!\d)(?:\+\d{1,3}[ -])?(?:\(\d{3}\)|\d{3})[ -]\d{3}[ -]\d{4}(?!\d)",
    "credential": r"\bsk-[A-Za-z0-9_-]{12,}",
    "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    "identity_label": r"(?im)^\s*(?:full\s+name|name|home\s+address|address|email|phone|telephone)\s*:",
}


def privacy_check(texts):
    """Reject common direct identifiers without logging matched text.

    This pattern check is not a guarantee that natural-language text is anonymous.
    Clinical content needed for the approved research is intentionally retained.
    """
    for text in texts:
        for kind, pattern in PRIVATE_PATTERNS.items():
            if re.search(pattern, text):
                raise ValueError("outgoing privacy check requires review: " + kind)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise RuntimeError("API redirects are disabled")


def api_transport(operation, body, api_key=None):
    """Credentials supplied in memory only; no environment or credential file."""
    if operation not in ("chat/completions", "embeddings"):
        raise ValueError("unsupported API operation")
    if not api_key:
        raise RuntimeError("an interactive one-time API key is required")
    privacy_check(body["input"] if operation == "embeddings" else [m["content"] for m in body["messages"]])
    request = urllib.request.Request("https://api.openai.com/v1/" + operation,
        data=json.dumps(body, ensure_ascii=False).encode(), method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=180) as response:
            return json.load(response)
    finally:
        request.remove_header("Authorization")


class OneTimeKey:
    """Never export the key, include it in repr, or persist it in run receipts."""
    def __init__(self):
        self._key = None

    def read(self):
        if not sys.stdin.isatty():
            raise RuntimeError("use docker exec -it in your terminal; hidden input requires a TTY")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            self._key = getpass.getpass("OpenAI API key (hidden, this run only): ").strip()
        if not self._key:
            raise ValueError("empty API key; no request sent")

    def __call__(self, operation, body):
        return api_transport(operation, body, api_key=self._key)

    def clear(self):
        self._key = None


def checked_pathology(value):
    for key in ("core_condition", "compliance_lever", "risk_needed"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise ValueError("missing pathology field: " + key)
    if value["risk_needed"] not in {"None", "Low", "High", "Immediate"}:
        raise ValueError("invalid pathology risk_needed")
    for key in ("distortions", "keywords"):
        if not isinstance(value.get(key), list) or not all(isinstance(v, str) and v.strip() for v in value[key]):
            raise ValueError("invalid pathology list: " + key)
    return value


def pipeline(goals, vera, candidates, cache, output, synthetic=False):
    """Phase-I retrieval with a source-locked builder and compatibility gate.

    A synthetic injected transport tests software only. It is never a fallback
    for failed model calls, embeddings, filtering or historical missing data.
    """
    output = Path(output)
    protect_old_pilot(output)
    decisions, kept = [], []
    for goal in goals:
        decision = cache.chat("client_filter", [{"role": "system", "content": CLIENT_SYSTEM},
                              {"role": "user", "content": goal["goal"][:400]}], 30)
        if any(decision.get(k) not in ("yes", "no") for k in ("is_client_utterance", "is_request")):
            raise ValueError("client classification must explicitly say yes or no; errors are not exclusions")
        row = {**goal, **{k: decision[k] == "yes" for k in ("is_client_utterance", "is_request")}}
        decisions.append(row)
        if row["is_client_utterance"]:
            kept.append(row)
    source.write_once(output / "client_decisions.jsonl", source.jsonl_bytes(decisions))
    source.write_once(output / "client_goals.jsonl", source.jsonl_bytes(kept))
    profiles = []
    for goal in kept:
        value = cache.chat("pathology", [{"role": "system", "content": PATHOLOGY_SYSTEM},
            {"role": "user", "content": f"crisis_label={goal['crisis_label']}\nMESSAGE: {goal['goal'][:400]}"}], 220)
        profiles.append({**goal, "pathology": checked_pathology(value)})
    source.write_once(output / "goal_pathology.jsonl", source.jsonl_bytes(profiles))
    routed, builds, contracts, compatibility, rejected_builds = [], [], [], [], []
    if profiles:
        vtexts, ctexts = pool_texts(vera, candidates)
        routed = rank_candidates(profiles, vera, candidates, cache.embed(vtexts), cache.embed(ctexts),
                                 cache.embed([pathtext(g["pathology"]) for g in profiles]), topk=3)
        source.write_once(output / "routed_candidates.jsonl", source.jsonl_bytes(routed))
        pools = {"VERA-SI": {p["Name"]: p for p in vera}, "Cactus": {p["persona_id"]: p for p in candidates}}
        for goal, route in zip(profiles, routed):
            entries = [{"candidate": c, "persona": pools[c["source"]][c["id"]]} for c in route["persona_candidates"]]
            case = {"goal": goal, "pathology": goal["pathology"], "candidates": entries}
            selected = entries[0]
            contract = build_contract(case)
            contracts.append(contract)
            compatibility.append({"goal_id": goal["goal_id"], "source": selected["candidate"]["source"],
                                  "persona_id": selected["candidate"]["id"], **contract["compatibility"]})
            if contract["compatibility"]["status"] != "NO_EXPLICIT_CONFLICT":
                continue
            built = assemble_build(case, cache.chat("builder", build_locked_messages(case), 900))
            if built["validation"]["status"] == "blocked_generated_fact_claims":
                rejected_builds.append(built)
                continue
            builds.append({"goal_id": goal["goal_id"], "goal": goal["goal"],
                "crisis_label": goal["crisis_label"], "source": selected["candidate"]["source"],
                "persona_id": selected["candidate"]["id"], "selected_persona": selected["persona"],
                **built,
                "generated_text_status": "injected channel only; human source fidelity/target/style review required",
                "resistance_status": "not independently extracted or clinically validated",
                "historical_reproduction": False, "synthetic_test_only": synthetic})
    source.write_once(output / "routed_candidates.jsonl", source.jsonl_bytes(routed))
    source.write_once(output / "source_contracts.jsonl", source.jsonl_bytes(contracts))
    source.write_once(output / "compatibility_decisions.jsonl", source.jsonl_bytes(compatibility))
    source.write_once(output / "build_rejections.jsonl", source.jsonl_bytes(rejected_builds))
    source.write_once(output / "phase1_personas.jsonl", source.jsonl_bytes(builds))
    report = {"status": "synthetic_software_validation" if synthetic else "generated_pending_source_fidelity_review",
              "input_goals": len(goals), "accepted_client_goals": len(kept), "excluded": len(goals) - len(kept),
              "routed": len(routed), "candidate_links": sum(len(r["persona_candidates"]) for r in routed),
              "built_personas": len(builds), "historical_reproduction": False,
              "source_contract": CONTRACT_VERSION,
              "compatibility_statuses": dict(Counter(r["status"] for r in compatibility)),
              "blocked_generated_builds": len(rejected_builds), "semantic_fidelity_verified": False,
              "paper_dataset_reproduction": False, "target_model_calls": 0, "phase2_calls": 0,
              "request_usage": usage_report(cache.directory),
              "estimated_cost_reserved_usd": round(cache.reserved_cost, 12),
              "outputs": {p.name: {"sha256": cactus.sha256(p), "bytes": p.stat().st_size}
                          for p in output.glob("*.jsonl")}}
    write_json(output / "run_summary.json", report)
    return report


def usage_report(directory):
    requests, usage = Counter(), Counter()
    models = set()
    estimated_cost = 0.0
    for path in sorted(Path(directory).glob("*.response.json")):
        result = json.loads(path.read_text())["response"]
        request_path = path.with_name(path.name.replace(".response.json", ".request.json"))
        request = json.loads(request_path.read_text())
        requests[request["stage"]] += 1
        tokens = result.get("usage", {})
        if request["operation"] == "embeddings":
            estimated_cost += tokens.get("prompt_tokens", tokens.get("total_tokens", 0)) * PRICES["embedding_input"] / 1_000_000
        else:
            estimated_cost += (tokens.get("prompt_tokens", 0) * PRICES["chat_input"] +
                               tokens.get("completion_tokens", 0) * PRICES["chat_output"]) / 1_000_000
        if result.get("model"):
            models.add(result["model"])
        for key, value in result.get("usage", {}).items():
            if isinstance(value, int):
                usage[key] += value
    attempts = len(list(Path(directory).glob("*.request.json")))
    return {"successful_requests": dict(requests), "actual_models": sorted(models), "tokens": dict(usage),
            "total_attempts": attempts, "failed_or_uncertain": attempts - sum(requests.values()),
            "estimated_cost_from_reported_tokens_usd": round(estimated_cost, 12)}


def run(directory, execute=False, max_requests=0, max_cost_usd=0, prompt_api_key=False):
    manifest = load_run(directory)
    directory = run_directory(directory)
    if not execute:
        return plan(directory)
    if not 0 < max_requests <= 54:
        raise ValueError("approved pilot request budget must be between 1 and 54")
    if not math.isfinite(max_cost_usd) or not 0 < max_cost_usd <= 0.25:
        raise ValueError("approved estimated cost budget must be at most $0.25")
    if manifest["counts"]["pilot"] != 12:
        raise ValueError("only the 12-input pilot is approved")
    if not prompt_api_key:
        raise ValueError("use --prompt-api-key; credential files/environment are not used")
    with (directory / ".run.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with (directory / "vera.tsv").open(newline="", encoding="utf-8") as stream:
            vera = list(csv.DictReader(stream, delimiter="\t"))
        goals = read_jsonl(directory / "pilot_goals.jsonl")
        candidates = read_jsonl(directory / "cactus_candidates.jsonl")
        vt, ct = pool_texts(vera, candidates)
        privacy_check([g["goal"] for g in goals] + vt + ct +
                      [json.dumps(lock_source(p, "VERA-SI", p["Name"]), ensure_ascii=False) for p in vera] +
                      [json.dumps(lock_source(p, "Cactus", p["persona_id"]), ensure_ascii=False) for p in candidates])
        write_json(directory / "authorization_budget.json", {"max_requests": max_requests, "max_cost_usd": max_cost_usd})
        key = OneTimeKey()
        cache = RequestCache(directory, digest(manifest), key, max_requests, max_cost_usd)
        try:
            key.read()
            return pipeline(goals, vera, candidates, cache, directory)
        except Exception as error:
            write_json(directory / ("failure_" + str(cache.previous_attempts + cache.sent) + ".json"),
                       {"status": "stopped", "error_type": type(error).__name__,
                        "usage": usage_report(cache.directory), "estimated_cost_reserved_usd": cache.reserved_cost})
            raise
        finally:
            key.clear()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--per-label", type=int, default=2)
    p = commands.add_parser("plan")
    p.add_argument("--run-dir", type=Path, required=True)
    p = commands.add_parser("run")
    p.add_argument("--run-dir", type=Path, required=True)
    p.add_argument("--execute", action="store_true")
    p.add_argument("--prompt-api-key", action="store_true")
    p.add_argument("--max-requests", type=int, default=0)
    p.add_argument("--max-cost-usd", type=float, default=0)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        result = prepare(args.raw, args.source_dir, args.run_dir, args.per_label)
    elif args.command == "plan":
        result = plan(args.run_dir)
    else:
        result = run(args.run_dir, args.execute, args.max_requests, args.max_cost_usd, args.prompt_api_key)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Avoid dumping stack frames, HTTP headers, or provider error payloads.
        print("Stopped: " + type(error).__name__ + ". Inspect run receipts; no automatic retries.", file=sys.stderr)
        sys.exit(1)
