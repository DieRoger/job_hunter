import sys,io,json
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
from knowledge.resume_kb import ResumeKB
kb=ResumeKB()
data=json.loads(open('evaluation/datasets/eval_v1.json',encoding='utf-8').read())
for p in data["pairs"]:
    r=p["resume"]
    text=f"# {r['name']}\n{r['summary']}\nSkills: {' '.join(r['skills'])}\n"
    text+=" ".join(f"{e['company']}:{e['position']} {'; '.join(e['highlights'])}" for e in r["experiences"])
    kb.add_resume(text,source="eval",tags=[p["industry"]])
print(f"KB: {kb.stats}")

r=kb.hybrid_search("Python FastAPI Docker backend",top_k=3)
print(f"\nHybrid Search: {len(r)} results")
for i,c in enumerate(r):
    print(f"  {i+1}. [{c['type']}] s={c['hybrid_score']:.2f} | {c['text'][:100]}")
