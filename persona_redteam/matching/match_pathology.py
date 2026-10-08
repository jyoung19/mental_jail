"""Connect goal-pathology <-> persona-pathology to shortlist vulnerable personas.

Two-stage matcher (pathology axis, NOT surface text):
  1. HARD FILTER by crisis_label routing + suicide-risk tier
       suicidal_ideation / self-harm -> VERA-MH SI pool
           suicidal_ideation -> risk in {High, Immediate}
           self-harm         -> risk in {Low, High, Immediate}
       anxiety / substance / risk_taking / violent -> Cactus pool
  2. RANK the eligible personas by cosine between the goal's pathology text and the
     persona's pathology text (if persona_pathology_*.jsonl exists) else the persona's
     raw descriptor text; return top-k candidates.

Note: cosine is a WITHIN-pool ranker only (scales differ across sources); candidate
QUALITY is judged separately by an LLM coherence check, not by cosine.

Inputs:
  --goals   outputs/goal_pathology_n813.jsonl           (needs `pathology`)
  --persona-pathology-dir outputs/                       (optional; persona_pathology_*.jsonl)
Output:
  outputs/goal_persona_routed_n813.jsonl

Usage:
    python matching/match_pathology.py --goals outputs/goal_pathology_n813.jsonl --topk 3
"""
from __future__ import annotations
import argparse, csv, json, math
from pathlib import Path
try:
    from . import embeddings
except ImportError:  # Direct script invocation.
    import embeddings

ROOT = Path(__file__).resolve().parents[1]
cos = lambda a, b: sum(x*y for x, y in zip(a, b)) / (math.sqrt(sum(x*x for x in a))*math.sqrt(sum(x*x for x in b))+1e-9)
ELIG = {"suicidal_ideation": {"High", "Immediate"}, "self-harm": {"Low", "High", "Immediate"}}
route = lambda lab: "VERA-SI" if lab in ("suicidal_ideation", "self-harm") else "Cactus"


def load_pools():
    with (ROOT / "personas/veramh_si_n100.tsv").open(encoding="utf-8", newline="") as stream:
        vera = list(csv.DictReader(stream, delimiter="\t"))
    with (ROOT / "personas/cactus_distress_n2000.jsonl").open(encoding="utf-8") as stream:
        cactus = [json.loads(line) for line in stream]
    vtexts, ctexts = pool_texts(vera, cactus)
    return vera, vtexts, cactus, ctexts


def pool_texts(vera, cactus):
    """Original descriptor rendering, also usable with explicitly named pools."""
    vtext = lambda p: (f"{p['Age']} {p['Gender']}. {p['Diagnoses and Symptoms']}. "
                       f"{p['Current Suicidal Thoughts and Behaviors']}. triggers:{p['Recent Triggers and Stressors']}. "
                       f"comm:{p['Primary Communication Style']}")[:600]
    ctext = lambda p: f"{p.get('descriptor','')}. {p.get('condition','')} {p.get('cognitive_distortion','')} {p.get('style_reference','')}"[:600]
    return [vtext(p) for p in vera], [ctext(p) for p in cactus]


def pathtext(d):
    dl = d.get("distortions") if isinstance(d.get("distortions"), list) else []
    kw = d.get("keywords") if isinstance(d.get("keywords"), list) else []
    return f"{d.get('core_condition','')}. {' '.join(dl)}. {' '.join(kw)}. {d.get('compliance_lever','')}"


def rank_candidates(goals, vera, cactus, vera_vec, cactus_vec, gv, topk=3):
    """Original routing/cosine algorithm, separated from embedding API calls."""
    if topk < 1 or len(goals) != len(gv) or len(vera) != len(vera_vec) or len(cactus) != len(cactus_vec):
        raise ValueError("invalid topk or vector/row alignment")
    vectors = [*vera_vec, *cactus_vec, *gv]
    dimensions = {len(v) for v in vectors}
    if not vectors or len(dimensions) != 1 or 0 in dimensions or any(
        any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in v)
        or not any(x != 0 for x in v) for v in vectors
    ):
        raise ValueError("embeddings must have consistent dimensions and finite nonzero vectors")
    out = []
    for g, v in zip(goals, gv):
        lab = g["crisis_label"]; pool = route(lab)
        if pool == "VERA-SI":
            elig = ELIG.get(lab)
            idx = [i for i in range(len(vera)) if (elig is None or vera[i]["Short Current Suicide Risk Level"] in elig)]
            sims = sorted(idx, key=lambda i: -cos(v, vera_vec[i]))[:topk]
            cands = [{"source": "VERA-SI", "id": vera[i]["Name"], "risk": vera[i]["Short Current Suicide Risk Level"],
                      "cos": round(cos(v, vera_vec[i]), 3)} for i in sims]
            rf = sorted(elig) if elig else "none"
        else:
            sims = sorted(range(len(cactus)), key=lambda i: -cos(v, cactus_vec[i]))[:topk]
            cands = [{"source": "Cactus", "id": cactus[i]["persona_id"], "risk": None,
                      "cos": round(cos(v, cactus_vec[i]), 3)} for i in sims]
            rf = "none"
        if len(cands) != topk:
            raise ValueError("not enough eligible personas for requested topk")
        out.append({**{k: g[k] for k in ("goal_id", "crisis_label", "goal", "pathology")},
                    "routed_pool": pool, "risk_filter": rf, "persona_candidates": cands})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--goals", required=True)
    ap.add_argument("--out", default=str(ROOT / "outputs/goal_persona_routed_n813.jsonl"))
    ap.add_argument("--topk", type=int, default=3)
    a = ap.parse_args()
    goals = [json.loads(l) for l in open(a.goals)]
    vera, vtexts, cactus, ctexts = load_pools()
    vera_vec = embeddings.embed_texts(vtexts)
    cactus_vec = embeddings.embed_texts(ctexts)
    gv = embeddings.embed_texts([pathtext(g.get("pathology", {})) for g in goals])
    out = rank_candidates(goals, vera, cactus, vera_vec, cactus_vec, gv, a.topk)
    Path(a.out).write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out) + "\n", encoding="utf-8")
    print("SAVED ->", a.out, f"({len(out)})", flush=True)


if __name__ == "__main__":
    main()
