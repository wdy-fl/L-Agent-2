"""CLI commands: slash-command dispatching for session management."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from agent.cli.select import select_prompt
from agent.storage.sqlite import SQLiteTimelineStore
from agent.timeline.models import CheckpointKind
from agent.timeline.resume import ResumeResult, resume
from agent.timeline.rewind import RewindResult, rewind
from agent.timeline.session_factory import create_session_with_default_branch


class CommandDispatcher:
    """Handles / prefixed commands."""

    def __init__(self, store: SQLiteTimelineStore, console: Console) -> None:
        self._store = store
        self._console = console
        self._session_id: str = ""
        self._branch_id: str = ""

    @property
    def session_id(self) -> str:
        return self._session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        self._session_id = value

    @property
    def branch_id(self) -> str:
        return self._branch_id

    @branch_id.setter
    def branch_id(self, value: str) -> None:
        self._branch_id = value

    async def dispatch(self, command: str) -> bool:
        """Dispatch a / command. Returns True if handled, False if not a command."""
        parts = command.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""

        handlers = {
            "/new": self._cmd_new,
            "/list": self._cmd_list,
            "/resume": self._cmd_resume,
            "/rewind": self._cmd_rewind,
            "/status": self._cmd_status,
            "/help": self._cmd_help,
        }

        handler = handlers.get(cmd)
        if handler is None:
            self._console.print(f"[red]Unknown command: {cmd}[/red]")
            return True
        await handler(arg)
        return True

    async def _cmd_new(self, arg: str) -> None:
        session = create_session_with_default_branch(self._store)
        self._session_id = session.session_id
        self._branch_id = session.active_branch_id
        self._console.print("[green]New session created.[/green]")

    async def _cmd_list(self, arg: str) -> None:
        sessions = self._store.list_sessions()
        if not sessions:
            self._console.print("[dim]No sessions found.[/dim]")
            return

        options = []
        session_ids = []
        for s in sessions:
            label = f"{s.session_id[:8]}... ({s.title or 'untitled'})"
            options.append(label)
            session_ids.append(s.session_id)

        choice = await select_prompt(options, title="Select session")
        if choice < 0:
            return

        selected_session_id = session_ids[choice]
        result = resume(self._store, selected_session_id)
        self._session_id = selected_session_id
        self._branch_id = result.branch_id
        self._console.print(f"[green]Resumed session {selected_session_id[:8]}...[/green]")

    async def _cmd_resume(self, arg: str) -> None:
        if arg:
            result = resume(self._store, arg)
            self._session_id = arg
            self._branch_id = result.branch_id
            self._console.print(f"[green]Resumed session {arg[:8]}...[/green]")
            return
        await self._cmd_list("")

    async def _cmd_rewind(self, arg: str) -> None:
        if not self._branch_id:
            self._console.print("[red]No active session.[/red]")
            return

        checkpoints = self._store.get_checkpoints_by_branch(self._branch_id)
        user_snapshots = [cp for cp in checkpoints if cp.kind == CheckpointKind.user_snapshot]

        if not user_snapshots:
            self._console.print("[dim]No checkpoints to rewind to.[/dim]")
            return

        options = [f"#{i+1}: {cp.name} (seq {cp.message_cursor})" for i, cp in enumerate(user_snapshots)]
        choice = await select_prompt(options, title="Select rewind point")
        if choice < 0:
            return

        selected_cp = user_snapshots[choice]
        result = rewind(self._store, self._session_id, selected_cp.checkpoint_id)
        self._branch_id = result.new_branch_id
        self._console.print(f"[green]Rewound. New branch: {result.new_branch_id[:8]}...[/green]")

    async def _cmd_status(self, arg: str) -> None:
        table = Table(title="Session Status", show_header=False)
        table.add_column("Key", style="bold")
        table.add_column("Value")
        table.add_row("Session", self._session_id[:8] + "..." if self._session_id else "none")
        table.add_row("Branch", self._branch_id[:8] + "..." if self._branch_id else "none")

        if self._branch_id:
            msgs = self._store.get_messages_by_branch(self._branch_id)
            runs = len([m for m in msgs if m.role == "user"])
            table.add_row("Turns", str(runs))

        self._console.print(table)

    async def _cmd_help(self, arg: str) -> None:
        self._console.print("[bold]Available commands:[/bold]")
        self._console.print("  /new      Create a new session")
        self._console.print("  /list     List and select a session")
        self._console.print("  /resume   Resume a session by ID")
        self._console.print("  /rewind   Rewind to a checkpoint")
        self._console.print("  /status   Show current session status")
        self._console.print("  /help     Show this help message")
