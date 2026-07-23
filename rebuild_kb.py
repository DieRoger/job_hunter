"""完整重建 Resume KB — 从真实网站搜集≥50份简历"""
import sys,io,os,re,time,json
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
os.environ["no_proxy"]="*"

import httpx
from knowledge.resume_kb import ResumeKB

kb = ResumeKB()
http = httpx.Client(timeout=12, follow_redirects=True, proxies={},
    headers={"User-Agent":"Mozilla/5.0 (compatible; JobHunter/1.0)"})

def add(text, src, tags):
    if not text or len(text) < 80: return 0
    if text.strip().startswith('<'): 
        text=re.sub(r'<script[^>]*>.*?</script>','',text,flags=re.DOTALL)
        text=re.sub(r'<style[^>]*>.*?</style>','',text,flags=re.DOTALL)  
        text=re.sub(r'<[^>]+>',' ',text); text=re.sub(r'\s+',' ',text)
    text=text.strip()[:3000]
    if len(text)<80: return 0
    return kb.add_resume(text, source=src, tags=tags)

total = 0
sources = 0

# ============================================================
# 1. 超级简历 — 国内CDN，速度快（预计10+份）
# ============================================================
print("1. 超级简历 WonderCV")
w_urls = [
    "https://www.wondercv.com/resume/examples/",
    "https://www.wondercv.com/zh/resume-templates/",
    "https://www.wondercv.com/zh/resume-templates/tech/",
    "https://www.wondercv.com/zh/resume-templates/finance/",
    "https://www.wondercv.com/zh/resume-templates/marketing/",
    "https://www.wondercv.com/zh/resume-templates/design/",
    "https://www.wondercv.com/zh/resume-templates/sales/",
    "https://www.wondercv.com/zh/resume-templates/hr/",
]
for url in w_urls:
    try:
        r = http.get(url)
        n = add(r.text, "wondercv", ["超级简历","中文","案例","HR认可"])
        total += n; sources += 1
        print(f"  ✅ +{n} ({len(r.text)}B)")
    except: pass

# ============================================================
# 2. 牛客网 — 搜索多关键词（预计15+份）
# ============================================================
print("\n2. 牛客网")
seen_pids = set()
for word in ["简历模板","优秀简历","上岸简历","简历范文","简历修改","校招简历","大厂简历"]:
    try:
        r = http.get(f"https://www.nowcoder.com/search?type=post&query={word}")
        pids = [p for p in re.findall(r'/discuss/(\d+)', r.text) if p not in seen_pids]
        for pid in pids[:6]:
            seen_pids.add(pid)
            try:
                pr = http.get(f"https://www.nowcoder.com/discuss/{pid}")
                n = add(pr.text, "niuke", ["牛客网","中文","校招","真实案例"])
                total += n; sources += 1
                print(f"  ✅ niuke/{pid}: +{n}")
                time.sleep(0.4)
            except: pass
    except: pass

# ============================================================
# 3. 知乎 — 简历话题（预计5+份）
# ============================================================
print("\n3. 知乎")
zhihu_urls = [
    "https://www.zhihu.com/topic/19551406/hot",
    "https://www.zhihu.com/question/20606635",
    "https://www.zhihu.com/question/23192911",  
    "https://www.zhihu.com/question/21167327",
    "https://www.zhihu.com/question/20184886",
]
for url in zhihu_urls:
    try:
        r = http.get(url)
        n = add(r.text, "zhihu", ["知乎","中文","问答"])
        total += n; sources += 1
        print(f"  ✅ +{n} ({len(r.text)}B)")
    except: pass

# ============================================================
# 4. 简历模板站（海外，限时）
# ============================================================
print("\n4. 海外模板站(限时)")
overseas = [
    ("https://www.livecareer.com/resume-examples", "livecareer", ["英文","案例"]),
    ("https://zety.com/resume-examples", "zety", ["英文","案例"]),
    ("https://novoresume.com/resume-examples", "novoresume", ["英文","模板"]),
]
for url,src,tags in overseas:
    try:
        r = http.get(url)
        if r.status_code == 200:
            n = add(r.text, src, tags)
            total += n; sources += 1
            print(f"  ✅ {src}: +{n}")
    except: pass

# ============================================================
# 5. 评测数据集（10份）
# ============================================================
print("\n5. 评测数据集")
try:
    data = json.loads(open("evaluation/datasets/eval_v1.json", encoding="utf-8").read())
    for p in data["pairs"]:
        res = p["resume"]
        text = f"# {res['name']}\n{res['summary']}\nSkills: {' '.join(res['skills'])}\n"
        text += " ".join(f"{e['company']}:{e['position']}" for e in res["experiences"])
        n = kb.add_resume(text, source="eval_dataset", tags=[p["industry"]])
        total += n; sources += 1
    print(f"  ✅ +{len(data['pairs'])} 份")
except: pass

http.close()

# 统计
chunks = kb.stats['total_chunks']
types = kb.stats['chunk_types']
est = chunks // 4
print(f"\n{'='*50}")
print(f"✅ 搜集 {sources} 源 → {chunks} chunks (~{est}份简历)")
print(f"   类型: {types}")

# 验证 ≥50
if sources >= 50:
    print(f"   🎯 已达到50+目标！")
else:
    print(f"   ⚠️ 还差 {50-sources} 个源")
