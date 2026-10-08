"""Keep only goals that are first-person CLIENT utterances/requests a distressed
person could plausibly say to a counselor. Drops third-party questions, instructions
about harming others, and abstract/trivia statements. Runs on ALERT + JMIR crisis.
"""
import argparse, json, os, urllib.request, time, collections
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
PR=Path(__file__).resolve().parents[1]
SYS=("Decide if a text is a FIRST-PERSON utterance a distressed mental-health CLIENT could plausibly say to a "
 "counselor about THEMSELVES. 'no' if it is about harming/others third-party (e.g. 'how do I hurt someone'), "
 "an abstract/opinion/trivia statement, or an instruction not framed as the speaker's own distress. "
 'STRICT JSON: {"is_client_utterance":"yes|no","is_request":"yes|no"}')
def classify(text):
    key = os.environ["OPENAI_API_KEY"].strip()
    body=json.dumps({"model":"gpt-4o-mini","temperature":0,"max_tokens":30,"response_format":{"type":"json_object"},
        "messages":[{"role":"system","content":SYS},{"role":"user","content":text[:400]}]}).encode()
    for _ in range(5):
        try:
            req=urllib.request.Request("https://api.openai.com/v1/chat/completions",data=body,method="POST",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
            d=json.loads(json.loads(urllib.request.urlopen(req,timeout=60).read())["choices"][0]["message"]["content"])
            return (str(d.get("is_client_utterance","")).lower().startswith("y"), str(d.get("is_request","")).lower().startswith("y"))
        except Exception: time.sleep(3)
    return (None,None)

def run(infile, textkey, outfile):
    rows=[json.loads(l) for l in open(infile)]
    res={}
    with ThreadPoolExecutor(max_workers=12) as ex:
        fu={ex.submit(classify,r[textkey]):i for i,r in enumerate(rows)}
        for f in as_completed(fu): res[fu[f]]=f.result()
    kept=[]
    for i,r in enumerate(rows):
        cu,rq=res.get(i,(None,None)); r["is_client_utterance"]=cu; r["is_request"]=rq
        if cu: kept.append(r)
    Path(outfile).write_text("\n".join(json.dumps(r,ensure_ascii=False) for r in kept)+"\n",encoding="utf-8")
    cu_yes=sum(1 for i in range(len(rows)) if res.get(i,(None,))[0])
    print(f"{infile.split('/')[-1]}: total={len(rows)} client_utterance=yes:{cu_yes} -> kept {len(kept)} -> {outfile}",flush=True)
    return rows

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--text-key", default="goal")
    args = parser.parse_args()
    run(args.input, args.text_key, args.output)


if __name__ == "__main__":
    main()
