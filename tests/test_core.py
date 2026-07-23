"""核心模块测试 — pytest"""
import sys,os,json
import pytest

# 不需要真实API的单元测试
class TestDomainRules:
    """Domain层纯函数测试"""

    def test_rule_score_perfect_match(self):
        from src.domain.rules import MatchingDomain
        score = MatchingDomain.rule_score(
            user_skills={"Python","Django","MySQL","Redis"},
            jd_skills={"Python","Django","MySQL","Redis"},
            user_years=5, jd_years=3,
            user_education="本科", jd_education="本科"
        )
        assert score == 100.0

    def test_rule_score_no_match(self):
        from src.domain.rules import MatchingDomain
        score = MatchingDomain.rule_score(
            user_skills={"Java","Spring"},
            jd_skills={"Python","Django","MySQL"},
            user_years=1, jd_years=5,
            user_education="大专", jd_education="硕士"
        )
        assert score < 50

    def test_weighted_final(self):
        from src.domain.rules import MatchingDomain
        final = MatchingDomain.weighted_final(80, 90, 70)
        assert 75 < final < 85  # 80*0.4+90*0.35+70*0.25=81

    def test_check_skill_inflation(self):
        from src.domain.rules import ResumeDomain
        ok, rate = ResumeDomain.check_skill_inflation(
            {"Python","Django"}, {"Python","Django","FastAPI"}
        )
        assert not ok
        assert rate == 0.5  # 1 new / 2 original

    def test_risk_level_high(self):
        from src.domain.rules import QADomain
        level = QADomain.assess_risk([
            {"type":"fabricated","severity":"high"}
        ])
        assert level == "high"

    def test_risk_level_low(self):
        from src.domain.rules import QADomain
        level = QADomain.assess_risk([
            {"type":"minor","severity":"low"},
            {"type":"minor","severity":"low"}
        ])
        assert level == "low"


class TestExceptions:
    """异常体系测试"""

    def test_base_exception(self):
        from src.exceptions import JobHunterError
        e = JobHunterError("test")
        assert e.code == "JH0000"
        assert "test" in str(e)

    def test_llm_error_codes(self):
        from src.exceptions import LLMAuthError, LLMRateLimitError, LLMTimeoutError
        assert LLMAuthError().code == "JH1002"
        assert LLMRateLimitError().code == "JH1003"
        assert LLMTimeoutError().code == "JH1004"

    def test_exception_dict(self):
        from src.exceptions import ValidationError
        e = ValidationError("bad data", {"field": "name"})
        d = e.to_dict()
        assert d["code"] == "JH3001"
        assert d["details"]["field"] == "name"


class TestSchemas:
    """Pydantic数据模型测试"""

    def test_user_profile_defaults(self):
        from src.models.schemas import UserProfile
        p = UserProfile(name="test")
        assert p.name == "test"
        assert p.skills == []
        assert p.total_years == 0.0

    def test_job_description(self):
        from src.models.schemas import JobDescription
        jd = JobDescription(title="Python后端", company="阿里",
                           skills_required=["Python","Django"])
        assert jd.title == "Python后端"
        assert len(jd.skills_required) == 2

    def test_career_direction(self):
        from src.models.schemas import CareerDirection, LearningItem, ProjectSuggestion
        d = CareerDirection(
            title="Python后端", match_score=85, match_reason="技能对口",
            learning_path=[LearningItem(topic="Redis", resource="官网", estimated_hours=10)],
            suggested_projects=[ProjectSuggestion(name="Demo", description="test")]
        )
        assert d.match_score == 85
        assert len(d.learning_path) == 1


class TestRepository:
    """Repository层测试"""

    def test_save_load(self, tmpdir):
        from src.repository.store import ProfileRepository
        repo = ProfileRepository(str(tmpdir))
        repo.save("test_user", {"name": "张三", "skills": ["Python"]})
        loaded = repo.load("test_user")
        assert loaded["name"] == "张三"
        assert loaded["skills"] == ["Python"]

    def test_exists(self, tmpdir):
        from src.repository.store import ProfileRepository
        repo = ProfileRepository(str(tmpdir))
        assert not repo.exists("nobody")
        repo.save("nobody", {})
        assert repo.exists("nobody")

    def test_delete(self, tmpdir):
        from src.repository.store import ProfileRepository
        repo = ProfileRepository(str(tmpdir))
        repo.save("tmp", {"x": 1})
        repo.delete("tmp")
        assert not repo.exists("tmp")

    def test_sqlite_save_load(self, tmpdir):
        from src.repository.sqlite_store import SQLiteProfileRepository
        db = str(tmpdir.join("test.db"))
        repo = SQLiteProfileRepository(db)
        repo.save("u1", {"name": "张三"})
        assert repo.exists("u1")
        assert repo.load("u1")["name"] == "张三"
        repo.close()


class TestSkillGraph:
    """技能图谱测试"""

    def test_alias_matching(self):
        from src.skill_graph.graph import SkillGraph
        g = SkillGraph()
        node = g.fuzzy_find("k8s")
        assert node is not None
        assert node.name == "Kubernetes"

    def test_cross_category_distance(self):
        from src.skill_graph.graph import SkillGraph
        g = SkillGraph()
        dist = g.distance("FastAPI", "Docker")
        assert dist > 0.5  # 不同分类远

    def test_sibling_distance(self):
        from src.skill_graph.graph import SkillGraph
        g = SkillGraph()
        sim = g.similarity("FastAPI", "Flask")
        assert sim > 0.3  # 同父节点近

    def test_graph_score(self):
        from src.skill_graph.graph import SkillGraph
        g = SkillGraph()
        score = g.compute_graph_score(
            ["Python","Django","MySQL"],
            ["Python","FastAPI","PostgreSQL"]
        )
        assert score > 50  # 相关技能应有合理分


class TestSharedContext:
    """SharedContext测试"""

    def test_defaults(self):
        from src.workflow.shared_context import SharedContext
        ctx = SharedContext()
        assert not ctx.has_profile()
        assert not ctx.has_jobs()
        assert ctx.qa_risk_level == "low"

    def test_profile_set(self):
        from src.workflow.shared_context import SharedContext
        from src.models.schemas import UserProfile
        ctx = SharedContext()
        ctx.profile = UserProfile(name="test")
        assert ctx.has_profile()

    def test_summary(self):
        from src.workflow.shared_context import SharedContext
        ctx = SharedContext(user_id="u1")
        s = ctx.summary()
        assert s["user"] == "u1"
        assert s["has_profile"] == False


class TestMemory:
    """UserMemory测试"""

    def test_preferences(self, tmpdir):
        from src.utils.memory import UserMemory
        m = UserMemory("test", str(tmpdir))
        m.set_preference("city", "北京")
        assert m.get_preference("city") == "北京"

    def test_record_apply(self, tmpdir):
        from src.utils.memory import UserMemory
        m = UserMemory("test", str(tmpdir))
        m.record_apply("j1", "腾讯", "Python")
        assert m.stats["total_applied"] == 1

    def test_skill_summary(self, tmpdir):
        from src.utils.memory import UserMemory
        from src.models.schemas import UserProfile, Skill
        m = UserMemory("test", str(tmpdir))
        m.profile = UserProfile(name="test", skills=[
            Skill(name="Python", level="精通", years=3)
        ])
        assert "Python" in m.skill_summary


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
