"""
Job Hunter V3 — AI 智能求职助手
用法: python run.py [命令]
"""

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ── Repository 单行切换 ──

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.agents.ats_agent import ATSAnalyzer
from src.agents.career_agent import CareerAgent
from src.agents.interview_agent import InterviewAgent
from src.agents.optimize_agent import GreetingAgent, QAAgent, ResumeOptimizeAgent
from src.agents.planner import PlannerAgent
from src.agents.resume_agent import ResumeAgent, ask_missing_info
from src.agents.reviewer_agent import ReviewerAgent
from src.exporter.dashboard import DashboardBuilder
from src.exporter.renderer import ResumeRenderer
from src.llm.resilience import CostMonitor
from src.models.schemas import JobDescription, UserProfile
from src.repository.sqlite_store import SQLiteProfileRepository
from src.repository.store import ProfileRepository as JSONProfileRepo
from src.utils.memory import UserMemory
from src.workflow.context import WorkflowContext
from src.workflow.reflection import ReflectionWorkflow
from src.workflow.shared_context import SharedContext


def get_repo() -> SQLiteProfileRepository | JSONProfileRepo:
    """返回 SQLite Repository（自动从 JSON 迁移数据）"""
    sqlite_repo = SQLiteProfileRepository()
    json_repo = JSONProfileRepo()
    # 如果 SQLite 为空但 JSON 有数据，迁移
    if not sqlite_repo.list_keys() and json_repo.list_keys():
        console.print("[yellow]🔄 从 JSON 迁移数据到 SQLite...[/yellow]")
        for key in json_repo.list_keys():
            data = json_repo.load(key)
            if data:
                sqlite_repo.save(key, data)
        console.print(f"[green]✅ 迁移 {len(json_repo.list_keys())} 条数据[/green]")
    return sqlite_repo

app = typer.Typer(name="job-hunter", help="AI 智能求职助手", add_completion=False)
console = Console()
cost = CostMonitor.get_instance()

# ═══════════════════════════════════════════════════════
@app.command()
def init(
    file: str = typer.Option(None, "--file", "-f", help="简历文件路径（Markdown/PDF/Word）"),
    name: str = typer.Option("default", "--name", "-n", help="画像名称"),
):
    """📝 录入简历 → 生成结构化用户画像"""
    if file:
        resume_text = Path(file).read_text(encoding="utf-8")
        console.print(f"[dim]📄 读取: {file} ({len(resume_text)} 字)[/dim]")
    else:
        console.print("[yellow]请输入简历文本（Markdown格式，空行结束）:[/yellow]")
        lines = []
        while True:
            line = input()
            if line == "": break
            lines.append(line)
        resume_text = "\n".join(lines)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), transient=True) as progress:
        progress.add_task("[cyan]DeepSeek 解析中...[/cyan]", total=None)
        agent = ResumeAgent()
        result = agent.run(WorkflowContext(), resume_text=resume_text, profile_name=name)

    if not result.success:
        console.print(f"[red]❌ {result.error}[/red]")
        return

    profile = result.data
    console.print(f"[green]✅ 画像已保存[/green] [bold]{profile.name}[/bold]")
    console.print(f"   📍 {profile.city} | 💼 {profile.current_position} | ⏳ {profile.total_years}年")
    console.print(f"   🛠️ {len(profile.skills)} 技能 | 🏢 {len(profile.experiences)} 段经历 | 📦 {len(profile.projects)} 个项目")

    missing = ask_missing_info(profile)
    if missing:
        console.print("\n[yellow]⚠️  建议补充:[/yellow]")
        for q in missing:
            console.print(f"   · {q}")

# ═══════════════════════════════════════════════════════
@app.command()
def discover(
    name: str = typer.Option("default", "--name", "-n", help="画像名称"),
):
    """🎯 推荐5个岗位方向 + 学习路径 + 项目建议"""
    repo = get_repo()
    if not repo.exists(name):
        console.print(f"[red]❌ 画像 [{name}] 不存在，请先 init[/red]")
        return

    console.print(f"[dim]🔍 为用户 [{name}] 分析岗位方向...[/dim]")
    agent = CareerAgent()
    reviewer = ReviewerAgent()

    with Progress(SpinnerColumn(), TextColumn("[cyan]DeepSeek 分析中...[/cyan]"), transient=True) as progress:
        progress.add_task("", total=None)
        result = agent.run(WorkflowContext(), profile_name=name)

    if not result.success:
        console.print(f"[red]❌ {result.error}[/red]")
        return

    directions = reviewer.review_career_directions(WorkflowContext(), result.data)

    table = Table(title="🎯 推荐岗位方向", border_style="cyan")
    table.add_column("#", style="dim")
    table.add_column("岗位", style="bold cyan")
    table.add_column("匹配度", style="green")
    table.add_column("技能缺口", style="yellow")
    table.add_column("时间线")

    for i, d in enumerate(directions, 1):
        table.add_row(
            str(i), d.title, f"{d.match_score}%",
            ", ".join(d.skill_gaps[:3]) if d.skill_gaps else "无",
            d.timeline[:50] + "..." if len(d.timeline) > 50 else d.timeline
        )
    console.print(table)

    for i, d in enumerate(directions[:3], 1):
        console.print(Panel(
            f"[bold]{d.title}[/bold] ({d.match_score}%)\n\n"
            f"[dim]匹配理由:[/dim] {d.match_reason[:120]}...\n"
            f"[dim]简历建议:[/dim] {d.resume_advice[:150]}...\n"
            f"[dim]推荐项目:[/dim] {len(d.suggested_projects)}个 | [dim]学习路径:[/dim] {len(d.learning_path)}项",
            title=f"详情 #{i}"
        ))

# ═══════════════════════════════════════════════════════
@app.command()
def optimize(
    name: str = typer.Option("default", "--name", "-n", help="画像名称"),
    direction: str = typer.Option(None, "--direction", "-d", help="方向编号，逗号分隔"),
    output: str = typer.Option("export", "--output", "-o", help="输出目录"),
):
    """✨ 针对方向优化简历 + ATS分析 + 生成招呼语"""
    repo = get_repo()
    if not repo.exists(name):
        console.print(f"[red]❌ 画像 [{name}] 不存在[/red]")
        return

    profile = UserProfile(**repo.load(name))
    career = CareerAgent()
    ctx = WorkflowContext()

    # 获取方向
    with Progress(SpinnerColumn(), TextColumn("[cyan]分析方向...[/cyan]"), transient=True) as progress:
        progress.add_task("", total=None)
        result = career.run(ctx, profile_name=name)

    if not result.success:
        console.print(f"[red]❌ {result.error}[/red]")
        return

    directions = result.data
    console.print(f"\n[bold]可选方向:[/bold]")
    for i, d in enumerate(directions, 1):
        console.print(f"  {i}. [cyan]{d.title}[/cyan] ([green]{d.match_score}%[/green])")

    if direction:
        picks = [int(x.strip()) - 1 for x in direction.split(",")]
    else:
        choice = typer.prompt("\n选择方向编号（逗号分隔，回车=全部）", default="")
        picks = [int(x.strip()) - 1 for x in choice.split(",")] if choice else list(range(len(directions)))

    reflection = ReflectionWorkflow(max_iterations=3, target_risk="low")
    greeting_agent = GreetingAgent()
    ats_agent = ATSAnalyzer()
    renderer = ResumeRenderer()

    for idx in picks:
        if idx >= len(directions): continue
        d = directions[idx]
        mock_jd = JobDescription(
            title=d.title, company=f"目标-{d.title}",
            skills_required=d.skill_gaps[:5] if d.skill_gaps else ["Python"],
            hard_skills=d.skill_gaps if d.skill_gaps else [],
        )

        console.print(f"\n[bold cyan]🔧 {d.title}[/bold cyan]")
        with Progress(SpinnerColumn(), TextColumn("[cyan]优化+审查+分析...[/cyan]"), transient=True) as progress:
            progress.add_task("", total=None)
            ref_result = reflection.optimize_with_reflection(name, mock_jd, ctx)

        if not ref_result.success:
            console.print(f"  [red]❌ {ref_result.error}[/red]")
            continue

        optimized = ref_result.data
        iterations = ref_result.extra.get("iterations", 1) if ref_result.extra else 1

        greet_result = greeting_agent.run(ctx, profile=profile, job=mock_jd)
        greeting = greet_result.data.content if greet_result.success and greet_result.data else ""

        ats_result = ats_agent.run(ctx, profile=profile, job=mock_jd, resume=optimized)
        ats_score = ats_result.data.get("ats_score", 0) if ats_result.success and ats_result.data else 0

        console.print(f"  [green]✅ QA={optimized.qa_risk_level}[/green] | ATS=[blue]{ats_score:.0f}[/blue] | 招呼={len(greeting)}字 | 迭代{iterations}轮")

        out_dir = Path(output) / d.title
        renderer.export_html(profile, out_dir / "简历.html", optimized=optimized)
        (out_dir / "招呼语.txt").write_text(greeting, encoding='utf-8')
        console.print(f"  [dim]📁 {out_dir}/[/dim]")

    console.print(f"\n[dim]💡 浏览器打开 HTML → Ctrl+P 打印 PDF[/dim]")

# ═══════════════════════════════════════════════════════
@app.command()
def export(
    name: str = typer.Option("default", "--name", "-n", help="画像名称"),
    template: str = typer.Option("professional", "--template", "-t", help="professional/modern"),
    output: str = typer.Option("", "--output", "-o", help="输出路径"),
):
    """📄 导出简历 HTML（浏览器打开 → 打印 PDF）"""
    repo = get_repo()
    if not repo.exists(name):
        console.print(f"[red]❌ 画像 [{name}] 不存在[/red]")
        return

    profile = UserProfile(**repo.load(name))
    renderer = ResumeRenderer()
    path = output or f"export/{name}_简历_{template}.html"
    renderer.export_and_open(profile, path, template=template)
    console.print(f"[green]✅ 已导出并打开[/green] [dim]{path}[/dim]")

# ═══════════════════════════════════════════════════════
@app.command()
def auto(
    file: str = typer.Option(None, "--file", "-f", help="简历文件路径"),
    name: str = typer.Option("default", "--name", "-n", help="画像名称"),
):
    """🚀 一键全流程: 画像→方向→优化→QA→ATS→招呼→导出"""
    console.print(Panel.fit("[bold cyan]🚀 Job Hunter V3 — 智能调度[/bold cyan]"))

    memory = UserMemory(name)
    shared = SharedContext(user_id=name)

    if file:
        resume_text = Path(file).read_text(encoding="utf-8")
        shared.resume_text = resume_text
        shared.profile_name = name
        resume_agent = ResumeAgent()
        result = resume_agent.run(WorkflowContext(), resume_text=resume_text, profile_name=name)
        if result.success:
            shared.profile = result.data
            memory.profile = result.data
            console.print(f"[green]✅ 画像 → SharedContext: {result.data.name}[/green]")
    elif memory.profile:
        shared.profile = memory.profile
        console.print(f"[green]✅ 画像 from Memory: {memory.profile.name}[/green]")
    else:
        console.print("[red]❌ 无画像，先运行 init[/red]")
        return

    planner = PlannerAgent()
    plan = planner.plan("full_pipeline", {
        "resume": ResumeAgent(), "career": CareerAgent(),
        "optimize": ResumeOptimizeAgent(), "qa": QAAgent(),
        "ats": ATSAnalyzer(), "greeting": GreetingAgent(),
    })
    console.print(f"[dim]📋 {len(plan.tasks)} 任务 | SharedContext 就绪[/dim]")

    result = planner.run(WorkflowContext(), plan=plan, shared=shared)

    if not shared.optimized_resume and shared.career_directions:
        top = shared.career_directions[0]
        mock_jd = JobDescription(title=top.title, company=f"目标-{top.title}",
                                 skills_required=top.skill_gaps[:5] if top.skill_gaps else ["Python"])
        ref = ReflectionWorkflow(3, "low")
        ref_result = ref.optimize_with_reflection(name, mock_jd, WorkflowContext())
        if ref_result.success:
            shared.optimized_resume = ref_result.data
            shared.qa_risk_level = shared.optimized_resume.qa_risk_level
        greet = GreetingAgent()
        gr = greet.run(WorkflowContext(), profile=shared.profile, job=mock_jd)
        if gr.success and gr.data:
            shared.greeting_message = gr.data.content if hasattr(gr.data, 'content') else str(gr.data)
        ats = ATSAnalyzer()
        ar = ats.run(WorkflowContext(), profile=shared.profile, job=mock_jd, resume=shared.optimized_resume)
        if ar.success and ar.data:
            shared.ats_score = ar.data.get("ats_score", 0)

    console.print(f"\n[green]✅ auto 完成[/green] | QA=[bold]{shared.qa_risk_level}[/bold] | ATS=[blue]{shared.ats_score:.0f}[/blue] | 招呼={len(shared.greeting_message)}字")

    if shared.optimized_resume and shared.profile:
        out_dir = Path("export") / "auto_output"
        renderer = ResumeRenderer()
        renderer.export_html(shared.profile, out_dir / "简历.html", optimized=shared.optimized_resume)
        (out_dir / "招呼语.txt").write_text(shared.greeting_message, encoding='utf-8')
        console.print(f"[dim]📁 {out_dir}/[/dim]")

    memory.save()
    _show_cost()

# ═══════════════════════════════════════════════════════
@app.command()
def interview(
    company: str = typer.Option("目标公司", "--company", "-c", help="公司名称"),
    position: str = typer.Option("Python后端", "--position", "-p", help="岗位名称"),
    resume: str = typer.Option(None, "--resume", "-r", help="简历文本（可选，用于生成针对性问题）"),
):
    """💬 模拟面试 — Question Graph 动态追问 + 评分"""
    from rich.prompt import Prompt

    agent = InterviewAgent()
    session = agent.start_session(company, position)
    console.print(f"[bold cyan]💬 模拟面试: {position} @ {company}[/bold cyan]")

    # 先生成 20 道题供参考
    questions = agent.generate_questions(
        JobDescription(title=position, company=company,
                       skills_required=["Python", "MySQL", "Redis", "Docker"]),
        count=10
    )
    if questions:
        console.print(f"\n[dim]📋 已生成 {len(questions)} 道准备题[/dim]")

    console.print(f"\n[bold]准备开始（共 5-8 题，每题系统评分）[/bold]\n")

    for round_num in range(1, 9):
        # 获取问题
        q = agent.ask_next(session)
        if q["type"] == "end":
            console.print(f"\n[bold green]🎉 面试结束！[/bold green]")
            break

        console.print(f"\n[bold cyan]Q{round_num} ({q['type']})[/bold cyan]")
        console.print(f"{q['question']}\n")

        answer = Prompt.ask("[dim]你的回答[/dim]")

        if not answer.strip():
            console.print("[yellow]跳过本题[/yellow]")
            continue

        # 评估
        eval_result = agent.evaluate_answer(session, q["question"], answer)
        score = eval_result.get("score", 50)
        feedback = eval_result.get("feedback", "")

        # 评分显示
        color = "green" if score >= 70 else "yellow" if score >= 50 else "red"
        console.print(f"  评分: [bold {color}]{score}[/bold {color}]")
        console.print(f"  反馈: [italic]{feedback}[/italic]")
        if eval_result.get("strengths"):
            console.print(f"  ✅ 优点: {', '.join(eval_result['strengths'][:2])}")
        if eval_result.get("improvements"):
            console.print(f"  📈 改进: {', '.join(eval_result['improvements'][:2])}")

    # 总结
    console.print(f"\n{'='*50}")
    total = len(session.history)
    avg = sum(h["score"] for h in session.history) / max(total, 1)
    console.print(f"[bold]📊 面试总结[/bold]")
    console.print(f"   答题: {total} 题 | 平均分: [bold]{avg:.0f}[/bold]")
    if session.weakness_tags:
        console.print(f"   弱项: {', '.join(set(session.weakness_tags[:5]))}")
    console.print(f"\n[dim]💾 会话已保存: {session.session_id}[/dim]")
    """💰 查看 Token/成本统计"""
    _show_cost()

# ═══════════════════════════════════════════════════════
@app.command()
def memory_cmd(
    name: str = typer.Option("default", "--name", "-n", help="用户标识"),
):
    """🧠 查看 Memory 统计"""
    memory = UserMemory(name)
    console.print(f"[bold cyan]🧠 Memory: {name}[/bold cyan]")
    stats = memory.stats

    table = Table(title="📊 统计")
    table.add_column("指标", style="dim")
    table.add_column("值", style="bold")
    for k, v in stats.items():
        table.add_row(k, str(v))
    console.print(table)

    if memory.profile:
        console.print(f"\n[bold]👤 {memory.profile.name}[/bold] | {memory.profile.current_position}")
    console.print(f"\n🛠️ 技能:")
    console.print(memory.skill_summary)

# ═══════════════════════════════════════════════════════
@app.command()
def dashboard(
    name: str = typer.Option("default", "--name", "-n", help="用户标识"),
):
    """📊 生成 Dashboard 看板（浏览器打开）"""
    import webbrowser
    builder = DashboardBuilder()
    memory = UserMemory(name)
    path = builder.export(name, f"reports/dashboard_{name}.html")
    webbrowser.open(f"file://{Path(path).absolute()}")
    console.print(f"[green]📊 Dashboard 已打开[/green] [dim]{path}[/dim]")
    console.print(f"   数据: {memory.stats['total_applied']}投递/{memory.stats['interviews']}面试/{memory.stats['offers']}Offer")

def _show_cost():
    console.print(Panel(cost.summary(), title="💰 Token/成本"))

if __name__ == "__main__":
    app()
