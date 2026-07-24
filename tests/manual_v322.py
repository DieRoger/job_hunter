"""Test V3.2.2: CompanyKB + Interview + SQLite"""
import io
import os
import sys

sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
os.environ["DEEPSEEK_API_KEY"]=""  # 请设置 DEEPSEEK_API_KEY 环境变量
os.environ["no_proxy"]="*"

# 1. SQLite Repository
print("="*50)
print("Test 1: SQLite Repository")
from src.repository.sqlite_store import SQLiteProfileRepository

repo = SQLiteProfileRepository()
repo.save("test_user", {"name":"张三","skills":["Python","Django"]})
loaded = repo.load("test_user")
print(f"  Save/Load: {loaded['name']} ({len(loaded['skills'])} skills)")
print(f"  Count: {repo.count()}")
print(f"  Query: {len(repo.query(limit=5))} entries")
repo.delete("test_user")
repo.close()

# 2. Company KB
print("\n"+"="*50)
print("Test 2: Company Knowledge Base")
from knowledge.company_kb import CompanyKB

ckb = CompanyKB()
# Test cache
data = ckb.get("腾讯", force_refresh=False)
print("  Company: 腾讯")
print(f"  Business: {data.get('business','?')[:60]}")
print(f"  Summary:  {ckb.summary_for_greeting('腾讯')[:80]}")

# 3. Interview Agent
print("\n"+"="*50)
print("Test 3: Interview Agent")
from src.agents.interview_agent import InterviewAgent

agent = InterviewAgent()
session = agent.start_session("腾讯", "Python后端开发", "test_session_001")
next_q = agent.ask_next(session)
print(f"  Q1: {next_q['question'][:80]}")
# Evaluate a mock answer
result = agent.evaluate_answer(session, next_q['question'], "我负责电商订单系统，使用Django+MySQL，日均处理10万订单，遇到性能瓶颈后通过Redis缓存和数据库读写分离将QPS提升3倍")
print(f"  Score: {result.get('score')}, Feedback: {result.get('feedback','')[:60]}")
# Load session
loaded_s = agent.load_session("test_session_001")
print(f"  Loaded session: {loaded_s is not None}, history: {len(loaded_s.history) if loaded_s else 0}")

print("\n✅ V3.2.2 All tests passed!")
