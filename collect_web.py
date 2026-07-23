"""从真实网站批量搜集简历 — 精简快速版"""
import sys,io,os,re,time
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
os.environ["no_proxy"]="*"

import httpx
from knowledge.resume_kb import ResumeKB

kb = ResumeKB()
http = httpx.Client(timeout=15, follow_redirects=True, proxies={})

def add(text, src, tags):
    if not text or len(text) < 80: return 0
    if text.strip().startswith('<'): 
        text=re.sub(r'<script[^>]*>.*?</script>','',text,flags=re.DOTALL)
        text=re.sub(r'<style[^>]*>.*?</style>','',text,flags=re.DOTALL)  
        text=re.sub(r'<[^>]+>',' ',text); text=re.sub(r'\s+',' ',text)
    text=text.strip()[:3000]
    if len(text)<80: return 0
    return kb.add_resume(text,source=src,tags=tags)

total = 0
count = 0

# ============================================================
# 1. 超级简历 — 国内CDN，速度快
# ============================================================
print("1. 超级简历 WonderCV")
wondercv_urls = [
    "https://www.wondercv.com/resume/examples/",
    "https://www.wondercv.com/zh/resume-templates/",
    "https://www.wondercv.com/zh/resume-templates/tech/",
    "https://www.wondercv.com/zh/resume-templates/finance/",
    "https://www.wondercv.com/zh/resume-templates/marketing/",
]
for url in wondercv_urls:
    try:
        r = http.get(url)
        n = add(r.text, "wondercv", ["超级简历","中文","案例","HR认可"])
        total += n; count += 1
        print(f"  ✅ +{n} chunks ({len(r.text)}B)")
    except Exception as e:
        print(f"  ❌ {e}")

# ============================================================
# 2. 牛客网 — 国内，速度快
# ============================================================
print("\n2. 牛客网 — 简历帖")
niuke_words = ["简历模板","优秀简历","上岸简历","简历范文","简历修改"]
for word in niuke_words:
    try:
        url = f"https://www.nowcoder.com/search?type=post&query={word}"
        r = http.get(url)
        # 提取帖子ID
        pids = list(set(re.findall(r'/discuss/(\d+)', r.text)))[:4]
        for pid in pids:
            try:
                pr = http.get(f"https://www.nowcoder.com/discuss/{pid}")
                n = add(pr.text, "niuke", ["牛客网","中文","校招","真实案例"])
                total += n; count += 1
                print(f"  ✅ niuke/{pid}: +{n} chunks")
                time.sleep(0.3)
            except: pass
    except Exception as e:
        print(f"  ❌ {e}")

# ============================================================
# 3. 海外简历模板站 — 速度快
# ============================================================
print("\n3. 海外简历模板站")
overseas = [
    ("https://www.livecareer.com/resume-examples", "livecareer", ["英文","案例","模板"]),
    ("https://zety.com/resume-examples", "zety", ["英文","案例"]),
    ("https://novoresume.com/resume-examples", "novoresume", ["英文","模板"]),
    ("https://www.myperfectresume.com/resume/examples", "myperfect", ["英文","案例"]),
    ("https://resumegenius.com/resume-samples", "resumegenius", ["英文","模板"]),
    ("https://www.monster.com/career-advice/resume-samples", "monster", ["英文","案例"]),
    ("https://www.indeed.com/career-advice/resume-samples", "indeed", ["英文","模板"]),
]
for url, src, tags in overseas:
    try:
        r = http.get(url)
        if r.status_code == 200:
            n = add(r.text, src, tags)
            total += n; count += 1
            print(f"  ✅ {src}: +{n} chunks")
        else:
            print(f"  ❌ {src}: HTTP{r.status_code}")
    except Exception as e:
        print(f"  ❌ {src}: {str(e)[:40]}")

# ============================================================
# 4. GitHub 直接下载已知仓库 (main分支)
# ============================================================
print("\n4. GitHub 已知简历仓库")
github_direct = [
    "https://raw.githubusercontent.com/posquit0/Awesome-CV/main/examples/resume.tex",
    "https://raw.githubusercontent.com/billryan/resume/main/resume.tex",  
    "https://raw.githubusercontent.com/sb2nov/resume/main/README.md",
]
for url in github_direct:
    try:
        r = http.get(url)
        if r.status_code == 200:
            n = add(r.text, "github", ["GitHub","模板","开源"])
            total += n; count += 1
            print(f"  ✅ +{n} chunks")
        else:
            print(f"  ❌ HTTP{r.status_code}")
    except Exception as e:
        print(f"  ❌ {e}")

http.close()

# 统计
total_chunks = kb.stats['total_chunks']
est = total_chunks // 4
types = kb.stats['chunk_types']
print(f"\n{'='*50}")
print(f"✅ 新增 {count} 源, {total} chunks")
print(f"   KB总计: {total_chunks} chunks (~{est}份简历)")
print(f"   类型: {types}")

# 实际数raw文件
import glob
raw_files = glob.glob("knowledge/resume_kb/raw/*.md")
print(f"   实际raw文件: {len(raw_files)} 份")
