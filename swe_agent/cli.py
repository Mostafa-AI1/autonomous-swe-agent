"""Interactive Command Line Interface (CLI) and Terminal UI for Autonomous SWE Agent."""

import json
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from swe_agent import __version__
from swe_agent.config import ExecutionMode, settings
from swe_agent.core.agent import SweAgent
from swe_agent.models.provider import ModelProvider
from swe_agent.sandbox.docker_sandbox import DockerSandbox
from swe_agent.sandbox.local_sandbox import LocalSandbox
from swe_agent.telemetry.tracer import TrajectoryLogger
from swe_agent.tools.registry import create_default_registry

from benchmark.evaluator import BenchmarkEvaluator
from benchmark.manifest import FROZEN_BENCHMARK_TASKS

app = typer.Typer(
    name="swe-agent",
    help="Production-grade Autonomous Software Engineering Agent with deterministic sandboxing and evaluation.",
    add_completion=False
)
console = Console()


def _print_banner():
    banner = f"""[bold cyan]
    +------------------------------------------------------------------+
    |                 AUTONOMOUS SWE AGENT v{__version__:<27}|
    |   Deterministic Sandboxing * FSM Reasoning * Benchmark Engine    |
    +------------------------------------------------------------------+
    [/bold cyan]"""
    console.print(banner)


@app.command()
def version():
    """Display system version, configured models, and environment settings."""
    _print_banner()
    table = Table(title="System Configuration", show_header=True, header_style="bold magenta")
    table.add_column("Property", style="dim", width=25)
    table.add_column("Value", style="cyan")

    table.add_row("Agent Version", __version__)
    table.add_row("Execution Mode", settings.execution_mode.value.upper())
    table.add_row("Primary Cloud Model", settings.primary_model)
    table.add_row("Local Fallback Model", settings.fallback_model)
    table.add_row("Max Steps Budget", str(settings.max_steps))
    table.add_row("Output Truncation Limit", f"{settings.max_tool_output_lines} lines")
    table.add_row("Sandbox Image", settings.sandbox_image)
    table.add_row("Trajectory Storage", str(settings.trajectory_dir))

    console.print(table)


@app.command()
def run(
    issue: str = typer.Option(..., "--issue", "-i", help="Issue description or task prompt to resolve"),
    repo: Path = typer.Option(Path("."), "--repo", "-r", help="Target repository directory to work inside"),
    mode: str = typer.Option("production", "--mode", "-m", help="Execution mode: 'production' (HITL) or 'benchmark' (headless)"),
    max_steps: int = typer.Option(30, "--max-steps", "-s", help="Step limit budget for the task"),
    model: Optional[str] = typer.Option(None, "--model", help="Override primary LLM model identifier"),
    use_docker: bool = typer.Option(False, "--docker", help="Force Docker container sandbox instead of local sandbox"),
):
    """Execute autonomous engineering agent on an assigned software issue."""
    _print_banner()

    exec_mode = ExecutionMode.BENCHMARK if mode.lower() == "benchmark" else ExecutionMode.PRODUCTION
    settings.execution_mode = exec_mode

    target_repo = repo.resolve()
    if not target_repo.exists():
        console.print(f"[bold red]Error: Target repository path '{target_repo}' does not exist.[/bold red]")
        raise typer.Exit(code=1)

    console.print(Panel(
        f"[bold white]{issue}[/bold white]\n\n"
        f"[dim]Repo: {target_repo} | Mode: {exec_mode.value.upper()} | Model: {model or settings.primary_model}[/dim]",
        title="[bold green]Assigned Engineering Task[/bold green]",
        border_style="green"
    ))

    # Initialize sandbox
    sandbox = None
    if use_docker:
        try:
            console.print("[dim]Initializing Docker Sandbox container...[/dim]")
            sandbox = DockerSandbox(workspace_dir=target_repo)
            sandbox.start()
        except Exception as exc:
            console.print(f"[yellow]Docker unavailable ({exc}). Falling back to LocalSandbox.[/yellow]")
            sandbox = LocalSandbox(workspace_dir=target_repo)
            sandbox.start()
    else:
        sandbox = LocalSandbox(workspace_dir=target_repo)
        sandbox.start()

    try:
        model_prov = ModelProvider(primary_model=model) if model else ModelProvider()
        tracer = TrajectoryLogger()
        agent = SweAgent(
            sandbox=sandbox,
            model_provider=model_prov,
            tool_registry=create_default_registry(),
            tracer=tracer,
            max_steps=max_steps
        )

        with console.status("[bold cyan]Agent is analyzing repository, planning, and executing tools...[/bold cyan]", spinner="dots"):
            state = agent.solve_issue(
                task_id=f"cli-task-{target_repo.name}",
                issue_statement=issue,
                repo_info=str(target_repo)
            )

        # Present Results
        if state.success:
            console.print(Panel(
                f"[bold green][PASS] TASK RESOLVED SUCCESSFULLY[/bold green]\n\n"
                f"[white]{state.conclusion_summary}[/white]\n\n"
                f"- Steps Taken: {state.step_count} / {state.max_steps}\n"
                f"- Modified Files: {', '.join(state.modified_files) if state.modified_files else 'None'}\n"
                f"- Self-Recovery Cycles: {state.recovery_attempts}",
                title="[bold green]Task Conclusion[/bold green]",
                border_style="green"
            ))
        else:
            console.print(Panel(
                f"[bold red][FAIL] TASK FAILED OR UNRESOLVED[/bold red]\n\n"
                f"[white]{state.conclusion_summary}[/white]\n\n"
                f"- Final Phase: {state.phase.value}\n"
                f"- Steps Taken: {state.step_count} / {state.max_steps}",
                title="[bold red]Task Conclusion[/bold red]",
                border_style="red"
            ))

        if state.final_patch:
            console.print("\n[bold cyan]Generated Unified Git Patch:[/bold cyan]")
            syntax = Syntax(state.final_patch, "diff", theme="monokai", line_numbers=True)
            console.print(syntax)

    finally:
        sandbox.stop()


@app.command()
def benchmark(
    task_id: Optional[str] = typer.Option(None, "--task", "-t", help="Evaluate specific task ID (evaluates all if omitted)"),
    model: Optional[str] = typer.Option(None, "--model", help="Model identifier to benchmark"),
):
    """Run custom SWE-bench-inspired evaluation suite in headless mode."""
    _print_banner()

    tasks_to_run = FROZEN_BENCHMARK_TASKS
    if task_id:
        tasks_to_run = [t for t in FROZEN_BENCHMARK_TASKS if t.task_id == task_id]
        if not tasks_to_run:
            console.print(f"[bold red]Task ID '{task_id}' not found in frozen manifest.[/bold red]")
            raise typer.Exit(code=1)

    console.print(f"[bold cyan]Launching Benchmark Evaluation on {len(tasks_to_run)} task(s)...[/bold cyan]\n")

    evaluator = BenchmarkEvaluator()
    model_prov = ModelProvider(primary_model=model) if model else None

    summary = evaluator.run_benchmark(tasks=tasks_to_run, model_provider=model_prov)

    # Render Rich Scoreboard Table
    table = Table(
        title="Custom SWE-bench-Inspired Scoreboard",
        show_header=True,
        header_style="bold blue",
        border_style="dim"
    )
    table.add_column("Task ID", style="white", width=28)
    table.add_column("Outcome", justify="center", width=12)
    table.add_column("Latency", justify="right", width=10)
    table.add_column("Tools", justify="right", width=8)
    table.add_column("Patch Delta", justify="right", width=12)
    table.add_column("Spurious Edits", justify="right", width=16)

    for res in summary.task_results:
        outcome = "[bold green]PASS[/bold green]" if res.resolved else "[bold red]FAIL[/bold red]"
        delta = f"+{res.lines_added}/-{res.lines_deleted}"
        table.add_row(
            res.task_id,
            outcome,
            f"{res.duration_seconds:.1f}s",
            str(res.tool_calls_total),
            delta,
            str(len(res.spurious_edits))
        )

    console.print(table)

    summary_panel = (
        f"[bold white]Resolution Rate (Pass@1):[/bold white] [bold green]{summary.resolution_rate:.1f}%[/bold green] ({summary.resolved_tasks}/{summary.total_tasks})\n"
        f"[bold white]Regression Rate:[/bold white]          {summary.regression_rate:.1f}%\n"
        f"[bold white]Self-Recovery Rate:[/bold white]       {summary.recovery_rate:.1f}%\n"
        f"[bold white]Avg Latency:[/bold white]              {summary.avg_duration_seconds:.2f}s\n"
        f"[bold white]Avg Tool Invocations:[/bold white]     {summary.avg_tool_calls:.1f}\n"
        f"[bold white]Total Tokens (In/Out):[/bold white]   {summary.total_prompt_tokens:,} / {summary.total_completion_tokens:,}\n"
        f"[bold white]Estimated Total Cost:[/bold white]    ${summary.total_cost_usd:.4f}"
    )
    console.print(Panel(summary_panel, title="[bold cyan]Consolidated Benchmark Summary[/bold cyan]", border_style="cyan"))


@app.command()
def inspect(
    trajectory_file: Path = typer.Argument(..., help="Path to the .jsonl trajectory file to inspect")
):
    """Inspect and post-mortem an agent execution trajectory."""
    _print_banner()

    if not trajectory_file.exists():
        console.print(f"[bold red]File not found: {trajectory_file}[/bold red]")
        raise typer.Exit(code=1)

    lines = trajectory_file.read_text(encoding="utf-8").strip().splitlines()
    if not lines:
        console.print("[yellow]Empty trajectory file.[/yellow]")
        return

    for idx, raw_line in enumerate(lines):
        record = json.loads(raw_line)
        rec_type = record.get("type", "")

        if rec_type == "METADATA":
            console.print(Panel(
                f"[bold cyan]Task ID:[/bold cyan] {record.get('task_id')}\n"
                f"[bold cyan]Repository:[/bold cyan] {record.get('repository')}\n"
                f"[bold cyan]Mode:[/bold cyan] {record.get('execution_mode')}\n"
                f"[bold cyan]Started:[/bold cyan] {record.get('started_at')}\n\n"
                f"[dim]{record.get('issue_statement')}[/dim]",
                title="[bold green]Trajectory Metadata[/bold green]",
                border_style="green"
            ))
        elif rec_type == "STEP":
            step_no = record.get("step_number")
            phase = record.get("phase")
            thought = record.get("thought", "(No explicit thought recorded)")
            tools = record.get("tool_calls", [])
            outputs = record.get("tool_outputs", [])

            tool_details = []
            for t, o in zip(tools, outputs):
                tool_details.append(f"- [bold magenta]{t.get('name')}[/bold magenta]({t.get('arguments')})\n  -> {str(o.get('output'))[:120]}...")

            console.print(Panel(
                f"[bold yellow]Phase: {phase}[/bold yellow]\n\n"
                f"[italic]{thought}[/italic]\n\n"
                f"[bold]Tool Invocations:[/bold]\n" + ("\n".join(tool_details) if tool_details else "None"),
                title=f"[bold]Step {step_no}[/bold]",
                border_style="blue"
            ))
        elif rec_type == "SUMMARY":
            status = "[bold green]SUCCESS[/bold green]" if record.get("success") else "[bold red]FAILED[/bold red]"
            console.print(Panel(
                f"Outcome: {status}\n"
                f"Duration: {record.get('total_duration_seconds')}s\n\n"
                f"Metrics: {json.dumps(record.get('metrics', {}), indent=2)}",
                title="[bold green]Final Outcome[/bold green]",
                border_style="green"
            ))


@app.command()
def demo(
    port: int = typer.Option(8000, "--port", "-p", help="Port to run demo dashboard on"),
    open_browser: bool = typer.Option(False, "--open", help="Automatically open web browser")
):
    """Launch the interactive Web UI and portfolio demonstration dashboard."""
    _print_banner()
    console.print(f"[bold green]Starting Interactive Portfolio Demo at: http://localhost:{port}[/bold green]")
    console.print("[dim]Includes: Goal-Directed FSM Pipeline, Real-Time Terminal, Diff Viewer, and 1-Click Instant Demo.[/dim]\n")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://localhost:{port}")
    from swe_agent.web.server import start_server
    start_server(port=port)


@app.command()
def web(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Bind host address"),
    port: int = typer.Option(8000, "--port", "-p", help="Bind port number")
):
    """Start the production FastAPI web dashboard server."""
    _print_banner()
    console.print(f"[bold cyan]Launching SWE Agent Web Dashboard on http://{host}:{port}[/bold cyan]")
    from swe_agent.web.server import start_server
    start_server(host=host, port=port)


if __name__ == "__main__":
    app()
