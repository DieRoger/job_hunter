"""
Interview Agent — V3.2.2
Question Graph 动态追问 + InterviewSession 状态持久化 + Mock Interview
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.llm.client import get_llm_client
from src.llm.resilience import CostMonitor
from src.models.schemas import JobDescription
from src.workflow.context import AgentResult, BaseAgent, WorkflowContext

# ─── Question Graph ─────────────────────────────────────

QUESTION_GRAPH: dict[str, dict[str, Any]] = {
    "start": {
        "type": "project",
        "question": "请介绍一下你最熟悉的一个项目，包括你的角色和技术栈。",
        "follow_ups": ["project_tech_deep", "project_challenge"],
    },
    "project_tech_deep": {
        "type": "project",
        "question": "这个项目中你遇到的最复杂的技术问题是什么？怎么解决的？",
        "follow_ups": ["project_arch", "system_design"],
    },
    "project_challenge": {
        "type": "project",
        "question": "项目中你和团队如何协作？有没有出现过意见分歧？",
        "follow_ups": ["behavior_conflict", "project_arch"],
    },
    "project_arch": {
        "type": "system_design",
        "question": "如果这个系统需要扩展到10倍用户量，你会从哪些方面入手？",
        "follow_ups": ["system_design", "coding"],
    },
    "system_design": {
        "type": "system_design",
        "question": "设计一个{system_desc}系统，请描述整体架构和关键组件。",
        "follow_ups": ["coding", "behavior_learning"],
    },
    "coding": {
        "type": "coding",
        "question": "请实现{code_task}，可以口述思路或伪代码。",
        "follow_ups": ["behavior_learning", "hr"],
    },
    "behavior_conflict": {
        "type": "behavior",
        "question": "描述一次你和同事/上级意见不同时你是如何处理的，结果如何？",
        "follow_ups": ["behavior_learning", "hr"],
    },
    "behavior_learning": {
        "type": "behavior",
        "question": "你最近学的一项新技术是什么？你是怎么学习的？",
        "follow_ups": ["hr"],
    },
    "hr": {
        "type": "hr",
        "question": "你为什么想加入我们公司？你对薪资和职业发展有什么期望？",
        "follow_ups": [],
    },
}


# ─── Interview Session ──────────────────────────────────

@dataclass
class InterviewSession:
    """面试会话状态 — 持久化，支持断点续答"""
    session_id: str = ""
    company: str = ""
    position: str = ""
    current_node: str = "start"
    history: list[dict[str, Any]] = field(default_factory=list)
    weakness_tags: list[str] = field(default_factory=list)
    overall_score: float = 0.0
    started_at: float = field(default_factory=time.time)
    completed: bool = False

    def add_answer(self, question: str, answer: str, score: float, feedback: str) -> None:
        self.history.append({
            "question": question,
            "answer": answer,
            "score": score,
            "feedback": feedback,
            "timestamp": time.time(),
        })
        if score < 60:
            self.weakness_tags.append(question[:30])

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "company": self.company,
            "position": self.position,
            "current_node": self.current_node,
            "history": self.history,
            "weakness_tags": self.weakness_tags,
            "overall_score": self.overall_score,
            "started_at": self.started_at,
            "completed": self.completed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> InterviewSession:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class InterviewAgent(BaseAgent):
    """
    面试模拟 Agent
    - Question Graph 动态追问
    - InterviewSession 持久化
    - 评分 + 反馈
    """

    name = "interview"
    description = "模拟面试官，基于JD动态追问并评分"

    def __init__(self, session_dir: str | Path | None = None):
        self._llm = get_llm_client()
        self._cost = CostMonitor.get_instance()
        if session_dir is None:
            session_dir = Path(__file__).parent.parent.parent / "knowledge" / "interview"
        self._session_dir = Path(session_dir)
        self._session_dir.mkdir(parents=True, exist_ok=True)

    def generate_questions(self, jd: JobDescription, count: int = 20) -> list[dict[str, str]]:
        """根据JD生成面试题（静态版，用于准备）"""
        prompt = f"""为以下岗位生成{count}道面试题，分四类：

岗位: {jd.title}
要求技能: {', '.join(jd.skills_required[:8] if jd.skills_required else jd.hard_skills[:8])}
公司: {jd.company}

分类: 算法/系统设计/项目深挖/行为面试
每题包含: category, question, reference_answer(要点)

输出JSON数组: [{{"category":"...","question":"...","reference":"..."}}]"""

        resp = self._llm.json(prompt, max_tokens=3000)
        self._cost.record(task="interview_gen", model=resp.model,
                          prompt_tokens=resp.usage.get("prompt_tokens", 0),
                          completion_tokens=resp.usage.get("completion_tokens", 0),
                          duration_ms=resp.duration_ms, cost_usd=resp.cost_usd)
        try:
            return json.loads(resp.content)
        except json.JSONDecodeError:
            return []

    def start_session(self, company: str, position: str,
                      session_id: str | None = None) -> InterviewSession:
        """开始新面试会话"""
        sid = session_id or f"interview_{int(time.time())}"
        session = InterviewSession(
            session_id=sid, company=company, position=position,
        )
        self._save_session(session)
        return session

    def ask_next(self, session: InterviewSession) -> dict[str, Any]:
        """获取下一个问题"""
        node = QUESTION_GRAPH.get(session.current_node)
        if not node or not node["follow_ups"]:
            return {"type": "end", "question": "面试结束！", "summary": self._summarize(session)}

        # 动态选择下一个节点
        import random
        next_node = random.choice(node["follow_ups"]) if node["follow_ups"] else None

        if next_node and next_node in QUESTION_GRAPH:
            session.current_node = next_node
            qnode = QUESTION_GRAPH[next_node]
            question = qnode["question"]
            # 替换模板变量
            question = question.replace("{system_desc}", "高并发电商")
            question = question.replace("{code_task}", "反转链表 或 实现一个LRU缓存")
        else:
            question = node["question"]

        self._save_session(session)
        return {"type": QUESTION_GRAPH.get(session.current_node, {}).get("type", "general"),
                "question": question, "node": session.current_node}

    def evaluate_answer(self, session: InterviewSession, question: str, answer: str) -> dict[str, Any]:
        """评估回答并给出分数+反馈"""
        prompt = f"""评估以下面试回答（0-100分）。

面试岗位: {session.position}
问题: {question}
回答: {answer[:500]}

输出JSON: {{"score": 75, "feedback": "具体反馈（30字）", "strengths": ["优点1"], "improvements": ["改进1"]}}"""

        resp = self._llm.json(prompt, max_tokens=300)
        self._cost.record(task="interview_eval", model=resp.model,
                          prompt_tokens=resp.usage.get("prompt_tokens", 0),
                          completion_tokens=resp.usage.get("completion_tokens", 0),
                          duration_ms=resp.duration_ms, cost_usd=resp.cost_usd)

        try:
            result = json.loads(resp.content)
        except json.JSONDecodeError:
            result = {"score": 50, "feedback": "评估异常"}

        session.add_answer(question, answer, result.get("score", 50),
                           result.get("feedback", ""))
        self._save_session(session)
        return result

    def mock_interview(self, session: InterviewSession,
                       user_answers: list[str]) -> dict[str, Any]:
        """运行完整模拟面试"""
        results = []
        questions = []

        for _i, answer in enumerate(user_answers):
            # 获取问题
            q = self.ask_next(session)
            if q["type"] == "end":
                break

            questions.append(q["question"])

            # 评估
            eval_result = self.evaluate_answer(session, q["question"], answer)
            results.append({"question": q["question"], "answer": answer, **eval_result})

        session.completed = True
        session.overall_score = sum(r["score"] for r in results) / max(len(results), 1)
        self._save_session(session)

        return {
            "session": session.to_dict(),
            "results": results,
            "overall_score": session.overall_score,
            "weakness_tags": session.weakness_tags,
        }

    def load_session(self, session_id: str) -> InterviewSession | None:
        """加载历史会话（断点续答）"""
        path = self._session_dir / f"{session_id}.json"
        if not path.exists():
            return None
        return InterviewSession.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def _save_session(self, session: InterviewSession) -> None:
        path = self._session_dir / f"{session.session_id}.json"
        path.write_text(json.dumps(session.to_dict(), ensure_ascii=False, indent=2),
                        encoding="utf-8")

    def _summarize(self, session: InterviewSession) -> str:
        """面试总结"""
        if not session.history:
            return "无面试记录"
        avg = sum(h["score"] for h in session.history) / len(session.history)
        return (f"面试完成！{len(session.history)}题，平均分{avg:.0f}。"
                f"弱项: {', '.join(session.weakness_tags[:3]) or '无'}")

    def execute(self, ctx: WorkflowContext, **kwargs: Any) -> AgentResult:
        questions = self.generate_questions(
            JobDescription(title=kwargs.get("position", "工程师"),
                           skills_required=kwargs.get("skills", []),
                           company=kwargs.get("company", "")),
            count=kwargs.get("count", 10),
        )
        return AgentResult.ok(questions)
