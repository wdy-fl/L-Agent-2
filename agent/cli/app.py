"""CLI main loop: typer entry + asyncio event loop."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Optional

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from rich.console import Console

from agent.cli.approval import ApprovalHandler
from agent.cli.commands import CommandDispatcher
from agent.cli.config import load_approval_config
from agent.cli.render import Renderer
from agent.config.settings import DEFAULT_CONFIG_PATHS, load_settings
from agent.core.context import RunContext
from agent.core.factory import build_runner
from agent.core.runner import AgentRunner
from agent.events import (
    ApprovalRequest,
    ModelDone,
    ModelStart,
    RunDone,
    RunError,
    Token,
    ToolDone,
    ToolStart,
)
from agent.home import initialize_agent_home
from agent.timeline.resume import resume
from agent.timeline.session_factory import create_session_with_default_branch
from agent.timeline.store import TimelineStore
from agent.tools.builtin import ALWAYS_CONFIRM_TOOLS, AUTO_APPROVE_TOOLS

app = typer.Typer(add_completion=False)
console = Console()


class CLISession:
    """Manages one interactive CLI session."""

    def __init__(
        self,
        runner: AgentRunner,
        store: TimelineStore,
        config_path: Path | None = None,
    ) -> None:
        self._runner = runner
        self._store = store
        self._console = console
        self._render = Renderer(console)

        config = load_approval_config(config_path)
        auto_approve = set(config.auto_approve) | AUTO_APPROVE_TOOLS
        always_confirm = set(config.always_confirm) | ALWAYS_CONFIRM_TOOLS
        self._approval = ApprovalHandler(console, auto_approve=auto_approve)
        self._always_confirm = always_confirm
        self._commands = CommandDispatcher(store, console)

        self._session_id: str = ""
        self._branch_id: str = ""
        self._interrupted = False

    def _handle_escape(self, event) -> None:
        del event
        self._interrupted = True

    async def start(self, session_id: str | None = None) -> None:
        """Start the CLI session."""
        if session_id:
            result = resume(self._store, session_id)
            self._session_id = session_id
            self._branch_id = result.branch_id
            self._console.print(f"[green]Resumed session {session_id[:8]}...[/green]")
        else:
            session = create_session_with_default_branch(self._store)
            self._session_id = session.session_id
            self._branch_id = session.active_branch_id

        self._commands.session_id = self._session_id
        self._commands.branch_id = self._branch_id

        self._console.print()
        self._console.print("[bold cyan]  L-Agent[/bold cyan] [dim]v0.1.0[/dim]")
        self._console.print("[dim]  Type your message to chat, /help for commands, Ctrl+C to exit.[/dim]")
        self._console.print()

        await self._main_loop()

    async def _main_loop(self) -> None:
        """Main input loop."""
        kb = KeyBindings()
        kb.add(Keys.Escape)(self._handle_escape)

        session: PromptSession = PromptSession(key_bindings=kb)

        while True:
            try:
                user_input = await session.prompt_async("❯ ")
            except EOFError:
                break
            except KeyboardInterrupt:
                self._console.print("[dim]Goodbye.[/dim]")
                break

            if not user_input.strip():
                continue

            if user_input.strip().startswith("/"):
                await self._commands.dispatch(user_input.strip())
                self._session_id = self._commands.session_id
                self._branch_id = self._commands.branch_id
                continue

            await self._handle_run(user_input.strip())

    async def _handle_run(self, user_input: str) -> None:
        """Execute an agent run and render events."""
        self._interrupted = False
        ctx = RunContext(
            input=user_input,
            session_id=self._session_id,
            branch_id=self._branch_id,
            timeline_store=self._store,
            home_client=self._store,
            auto_approve_tools=self._approval._auto_approve,
            always_confirm_tools=self._always_confirm,
        )

        start_time = time.time()

        async for event in self._runner.run(ctx):
            if self._interrupted:
                ctx.interrupted = True

            match event:
                case Token(text=t):
                    self._render.stream_text(t)
                case ModelStart():
                    pass
                case ModelDone():
                    self._render.finish_stream()
                case ToolStart(tool_name=name):
                    self._render.show_tool_spinner(name)
                case ToolDone(tool_name=name, result=r):
                    self._render.finish_tool(name, r)
                case ApprovalRequest() as req:
                    approved = await self._approval.prompt(req)
                    req.future.set_result(approved)
                case RunError(error=e):
                    self._render.show_error(e)
                case RunDone():
                    pass

        elapsed_ms = (time.time() - start_time) * 1000
        total_tokens = ctx.budget.consumed_total_tokens

        if ctx.interrupted:
            self._render.show_interrupted()
        elif ctx.status == "completed":
            self._render.show_status(ctx.iteration_index, total_tokens, elapsed_ms)


def _resolve_cli_config_path(config: str | None) -> Path:
    if config:
        return Path(config)
    for path in DEFAULT_CONFIG_PATHS:
        if path.exists():
            return path
    return Path("workspace/config.yaml")


@app.command()
def main(
    session: Optional[str] = typer.Option(None, "--session", "-s", help="Resume a session by ID"),
    config: Optional[str] = typer.Option(None, "--config", "-c", help="Config YAML path"),
) -> None:
    """L-Agent CLI - Interactive AI Agent."""
    config_path = _resolve_cli_config_path(config)
    settings = load_settings(config_path)
    home_client = initialize_agent_home(settings, config_path=config_path)
    runner = build_runner(config_path, home_client=home_client)

    cli_session = CLISession(runner, home_client, config_path)
    asyncio.run(cli_session.start(session_id=session))


if __name__ == "__main__":
    app()
