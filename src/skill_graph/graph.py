"""
技能图谱 — 树形技能结构 + 语义相似度匹配
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional


class SkillNode:
    """技能树节点"""
    def __init__(self, name: str, category: str = "", aliases: list[str] | None = None):
        self.name = name
        self.category = category
        self.aliases = aliases or []
        self.children: list[SkillNode] = []
        self.parent: SkillNode | None = None

    def add_child(self, child: "SkillNode") -> "SkillNode":
        child.parent = self
        self.children.append(child)
        return child

    def get_all_names(self) -> set[str]:
        """获取该节点及所有别名的名称集合"""
        names = {self.name.lower()}
        names.update(a.lower() for a in self.aliases)
        return names


class SkillGraph:
    """技能图谱 — 支持模糊匹配和层级关系"""

    def __init__(self):
        self._roots: dict[str, SkillNode] = {}
        self._index: dict[str, SkillNode] = {}  # 名称 → 节点索引
        self._build_default_graph()
        self._load_external_graph()  # 从 knowledge/graph.json 加载扩展

    def _build_default_graph_body(self):
        """构建默认技能树（节点定义）"""
        # 编程语言
        lang = self._add_root("编程语言")
        py = lang.add_child(SkillNode("Python", "编程语言", ["python3", "cpython"]))
        py.add_child(SkillNode("FastAPI", "框架"))
        py.add_child(SkillNode("Django", "框架", ["django rest framework"]))
        py.add_child(SkillNode("Flask", "框架"))
        py.add_child(SkillNode("SQLAlchemy", "ORM"))
        py.add_child(SkillNode("Celery", "任务队列"))
        py.add_child(SkillNode("asyncio", "异步"))

        go = lang.add_child(SkillNode("Go", "编程语言", ["golang"]))
        go.add_child(SkillNode("Gin", "框架"))
        go.add_child(SkillNode("Echo", "框架"))

        js = lang.add_child(SkillNode("JavaScript", "编程语言", ["js", "es6"]))
        js.add_child(SkillNode("React", "框架", ["reactjs"]))
        js.add_child(SkillNode("Vue", "框架", ["vuejs", "vue.js"]))
        js.add_child(SkillNode("Node.js", "运行时", ["node"]))

        # 数据库
        db = self._add_root("数据库")
        db.add_child(SkillNode("MySQL", "关系型"))
        db.add_child(SkillNode("PostgreSQL", "关系型", ["postgres"]))
        db.add_child(SkillNode("MongoDB", "文档型", ["mongo"]))
        db.add_child(SkillNode("Redis", "缓存", ["redis cluster"]))
        db.add_child(SkillNode("Elasticsearch", "搜索引擎", ["es"]))
        db.add_child(SkillNode("ClickHouse", "OLAP"))

        # 云计算/DevOps
        cloud = self._add_root("云计算")
        cloud.add_child(SkillNode("Docker", "容器"))
        cloud.add_child(SkillNode("Kubernetes", "编排", ["k8s"]))
        cloud.add_child(SkillNode("AWS", "云平台"))
        cloud.add_child(SkillNode("CI/CD", "持续集成", ["jenkins", "github actions"]))
        cloud.add_child(SkillNode("Nginx", "Web服务器"))

        # 大数据
        bigdata = self._add_root("大数据")
        bigdata.add_child(SkillNode("Spark", "计算", ["pyspark", "apache spark"]))
        bigdata.add_child(SkillNode("Hadoop", "存储", ["hdfs"]))
        bigdata.add_child(SkillNode("Kafka", "消息队列"))
        bigdata.add_child(SkillNode("Flink", "流处理"))

        # 软技能
        soft = self._add_root("软技能")
        soft.add_child(SkillNode("团队管理"))
        soft.add_child(SkillNode("技术方案设计"))
        soft.add_child(SkillNode("跨部门沟通"))

    def _add_root(self, name: str) -> SkillNode:
        node = SkillNode(name, "root")
        self._roots[name] = node
        return node

    def _build_default_graph(self):
        """构建默认技能树"""
        # ... (same as before)
        self._build_default_graph_body()
        self._reindex()  # 构建完统一索引所有节点

    def _reindex(self):
        """重建索引 — 遍历所有节点"""
        self._index.clear()

        def walk(node: SkillNode):
            self._index[node.name.lower()] = node
            for alias in node.aliases:
                self._index[alias.lower()] = node
            for child in node.children:
                walk(child)

        for root in self._roots.values():
            walk(root)

    def _load_external_graph(self):
        """从 knowledge/graph.json 加载技能图谱扩展"""
        import json
        from pathlib import Path
        graph_path = Path(__file__).parent.parent.parent / "knowledge" / "graph.json"
        if not graph_path.exists():
            return

        data = json.loads(graph_path.read_text(encoding="utf-8"))
        skills_data = data.get("skills", {})

        def add_node(parent: SkillNode | None, name: str, info: dict):
            node = SkillNode(name, info.get("category", ""), info.get("aliases", []))
            if parent:
                parent.add_child(node)
            return node

        for skill_name, skill_info in skills_data.items():
            category = skill_info.get("category", "")
            # 找到或创建根分类
            root = self._roots.get(category)
            if not root:
                root = self._add_root(category)
            pnode = add_node(root, skill_name, skill_info)
            # 递归添加子技能
            for child_name, child_info in skill_info.get("children", {}).items():
                cnode = add_node(pnode, child_name, child_info)
                for gchild_name, gchild_info in child_info.get("children", {}).items():
                    add_node(cnode, gchild_name, gchild_info)

        self._reindex()

    def find(self, name: str) -> SkillNode | None:
        """精确查找"""
        return self._index.get(name.lower())

    def fuzzy_find(self, name: str) -> SkillNode | None:
        """模糊查找 — 检查别名和子串"""
        name_lower = name.lower()
        if name_lower in self._index:
            return self._index[name_lower]

        # 遍历检查别名
        for node in self._index.values():
            if name_lower in node.get_all_names():
                return node

        return None

    def find_category(self, name: str) -> str:
        """查找技能所属分类"""
        node = self.fuzzy_find(name)
        if node:
            # 向上找根分类
            current = node
            while current.parent:
                current = current.parent
            for root_name, root_node in self._roots.items():
                if root_node is current:
                    return root_name
        return "其他"

    def distance(self, skill_a: str, skill_b: str) -> float:
        """
        计算两个技能在图谱中的距离（0=相同，1=完全不相关）
        同一父节点下的兄弟节点距离较近
        """
        node_a = self.fuzzy_find(skill_a)
        node_b = self.fuzzy_find(skill_b)

        if node_a is None or node_b is None:
            return 1.0

        # 相同节点
        if node_a is node_b:
            return 0.0

        # 找共同祖先
        ancestors_a = self._get_ancestors(node_a)
        ancestors_b = self._get_ancestors(node_b)

        # 找最深共同祖先
        for depth, ancestor in enumerate(ancestors_a):
            if ancestor in ancestors_b:
                # depth 是从 node_a 到共同祖先的距离
                depth_b = ancestors_b.index(ancestor)
                total_dist = depth + depth_b
                max_dist = len(ancestors_a) + len(ancestors_b)
                return total_dist / max(max_dist, 1)

        return 1.0

    def similarity(self, skill_a: str, skill_b: str) -> float:
        """技能相似度（0-1，1=完全相同）"""
        return 1.0 - self.distance(skill_a, skill_b)

    def _get_ancestors(self, node: SkillNode) -> list[SkillNode]:
        """获取从节点到根的路径"""
        path = []
        current: SkillNode | None = node
        while current is not None:
            path.append(current)
            current = current.parent
        return path

    def compute_graph_score(self, user_skills: list[str], jd_skills: list[str]) -> float:
        """
        基于技能图谱的匹配评分（0-100）
        对每个 JD 技能找到用户最匹配的技能，加权平均
        """
        if not jd_skills:
            return 50.0

        total_sim = 0.0
        for jd_skill in jd_skills:
            # 找用户技能中最相似的那个
            best_sim = max(
                (self.similarity(jd_skill, us) for us in user_skills),
                default=0.0,
            )
            total_sim += best_sim

        avg_sim = total_sim / len(jd_skills)
        return round(avg_sim * 100, 1)
