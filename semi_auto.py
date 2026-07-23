"""半自动爬虫 — 用户手动过验证码 → agent-browser自动采集"""
import io
import re
import subprocess
import sys
import time

sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')

# 复用 Playwright 的 Chromium
CHROME = r"C:\Users\john\AppData\Local\ms-playwright\chromium-1181\chrome-win\chrome.exe"

def run(cmd, timeout=30):
    """运行 agent-browser 命令"""
    env = {**__import__('os').environ, "AGENT_BROWSER_EXECUTABLE_PATH": CHROME, "no_proxy": "*"}
    try:
        r = subprocess.run(f"agent-browser {cmd}", shell=True, capture_output=True,
                          text=True, timeout=timeout, env=env)
        return r.stdout.strip()
    except subprocess.TimeoutExpired:
        return "(timeout)"

def wait_manual(platform):
    """等待用户手动过验证码"""
    input(f"\n⏳ 请在浏览器中完成 {platform} 的验证码/登录，完成后按回车继续...")

def scrape_boss(keyword="Python后端", city="北京"):
    """BOSS直聘半自动采集"""
    print("="*60)
    print(f"🔍 BOSS直聘: {keyword} {city}")
    print("="*60)
    
    # 1. 打开搜索页（有头模式，用户手动过验证）
    url = f"https://www.zhipin.com/web/geek/job?query={keyword}&city={city}"
    run(f"open {url} --headed")
    time.sleep(3)
    
    # 2. 等待用户过验证码
    wait_manual("BOSS直聘")
    
    # 3. 获取页面快照
    snap = run("snapshot -i")
    if not snap or "no interactive elements" in snap:
        print("  ⚠️ 页面无内容（可能仍需验证），跳过")
        return []
    
    # 4. 提取职位卡片
    jobs = []
    # 尝试用 extract 命令提取
    raw = run("extract --all")
    print(f"  原始数据: {len(raw)} 字符")
    
    # 用 snapshot 中的 ref 逐个提取
    lines = snap.split('\n')
    for line in lines:
        # 匹配类似 "link 'Python后端开发' [ref=e5]" 的行
        if 'ref=e' in line and any(k in line.lower() for k in ['开发','工程师','经理','架构','前端','后端','数据','测试','运维']):
            ref_match = re.search(r'\[ref=(e\d+)\]', line)
            if ref_match:
                ref = ref_match.group(1)
                text = run(f"extract {ref}")
                if text and len(text) > 5:
                    jobs.append({"ref": ref, "text": text[:200]})
    
    print(f"  ✅ 采集 {len(jobs)} 个职位")
    return jobs

def scrape_lagou(keyword="Python", city="北京"):
    """拉勾半自动采集"""
    print("\n" + "="*60)
    print(f"🔍 拉勾: {keyword} {city}")
    print("="*60)
    
    url = f"https://www.lagou.com/wn/jobs?kd={keyword}&city={city}"
    run(f"open {url} --headed")
    time.sleep(3)
    
    wait_manual("拉勾（滑块验证）")
    
    snap = run("snapshot -i")
    if not snap or "no interactive elements" in snap:
        print("  ⚠️ 页面无内容")
        return []
    
    # 提取
    jobs = []
    for line in snap.split('\n'):
        if 'ref=e' in line:
            ref_match = re.search(r'\[ref=(e\d+)\]', line)
            if ref_match:
                text = run(f"extract {ref_match.group(1)}")
                if text and len(text) > 3:
                    jobs.append({"ref": ref_match.group(1), "text": text[:200]})
    
    print(f"  ✅ 采集 {len(jobs)} 个职位")
    return jobs

# ============================================================
if __name__ == "__main__":
    print("""
╔══════════════════════════════════════════════╗
║   Job Hunter 半自动爬虫                       ║
║                                              ║
║   1. 浏览器窗口将打开（请勿关闭）              ║
║   2. 看到验证码 → 手动完成 → 按回车            ║
║   3. 程序自动采集页面数据                      ║
║   4. 自动翻页、去重、入库                      ║
╚══════════════════════════════════════════════╝
""")
    
    # 先关闭旧会话
    run("close")
    time.sleep(1)
    
    choice = input("选择平台 [1=BOSS直聘 2=拉勾 3=两个都爬]: ").strip()
    
    all_jobs = []
    if choice in ["1","3"]:
        boss = scrape_boss()
        all_jobs.extend(boss)
    if choice in ["2","3"]:
        lagou = scrape_lagou()
        all_jobs.extend(lagou)
    
    if all_jobs:
        print(f"\n{'='*60}")
        print(f"📊 共采集 {len(all_jobs)} 个职位")
        for i,j in enumerate(all_jobs[:10],1):
            print(f"  {i}. {j['text'][:100]}")
        
        # 入库
        save = input(f"\n💾 是否入库到 Resume KB? [y/N]: ").strip().lower()
        if save == 'y':
            from knowledge.resume_kb import ResumeKB
            kb = ResumeKB()
            for j in all_jobs:
                kb.add_resume(j['text'], source="semi-auto", tags=["爬虫","半自动"])
            print(f"  ✅ 已入库 {len(all_jobs)} 条")
    
    run("close")
    print("\n👋 完成！")
