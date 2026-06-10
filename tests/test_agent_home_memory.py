import asyncio
from typing import Any, cast

from rich.console import Console

from agent.cli.commands import CommandDispatcher
from agent.core.context import RunContext
from agent.steps.after_agent import AgentHomeRunFinalize
from agent.steps.before_agent import MemoryPrefetch
from agent.timeline.models import Branch, Checkpoint, CheckpointKind, RunStatus


class FakeHomeBase:
    def __init__(self):
        self.status_updates = []
        self.branch_updates = []
        self.checkpoints = [Checkpoint("c-runtime", "s1", "b1", "r1", CheckpointKind.runtime, "model_call_completed", 0)]

    def update_run_status(self, run_id, status):
        self.status_updates.append((run_id, status))

    def get_checkpoints_by_branch(self, branch_id):
        del branch_id
        return self.checkpoints

    def get_branch(self, branch_id):
        return Branch(branch_id=branch_id, session_id="s1")

    def update_branch(self, branch):
        self.branch_updates.append(branch)


class FakeHome(FakeHomeBase):
    def __init__(self):
        super().__init__()
        self.extractions = []

    def extract_memory(self, session_id, trigger):
        self.extractions.append((session_id, trigger))
        return {"status": "queued"}


class FakeHomeWithoutMemory(FakeHomeBase):
    pass


class FakeHomeWithNonCallableMemory(FakeHomeBase):
    extract_memory = "disabled"


def context_with_store(home, status="completed"):
    return RunContext(session_id="s1", branch_id="b1", run_id="r1", status=status, timeline_store=cast(Any, home))


def test_completed_run_updates_status_and_resume_head():
    home = FakeHome()
    ctx = context_with_store(home)

    AgentHomeRunFinalize(auto_extract_memory=False).run(ctx)

    assert home.status_updates == [("r1", RunStatus.completed)]
    assert home.branch_updates[0].resume_head == "c-runtime"


def test_failed_run_does_not_update_resume_head():
    home = FakeHome()
    ctx = context_with_store(home, status="failed")

    AgentHomeRunFinalize(auto_extract_memory=False).run(ctx)

    assert home.status_updates == [("r1", RunStatus.failed)]
    assert home.branch_updates == []


def test_auto_extract_only_when_enabled():
    home = FakeHome()
    ctx = context_with_store(home)

    AgentHomeRunFinalize(auto_extract_memory=True).run(ctx)

    assert home.extractions == [("s1", "after_agent")]


def test_auto_extract_is_skipped_when_store_does_not_support_memory_extraction():
    home = FakeHomeWithoutMemory()
    ctx = context_with_store(home)

    AgentHomeRunFinalize(auto_extract_memory=True).run(ctx)

    assert home.status_updates == [("r1", RunStatus.completed)]
    assert home.branch_updates[0].resume_head == "c-runtime"


def test_auto_extract_is_skipped_when_extract_memory_is_not_callable():
    home = FakeHomeWithNonCallableMemory()
    ctx = context_with_store(home)

    AgentHomeRunFinalize(auto_extract_memory=True).run(ctx)

    assert home.status_updates == [("r1", RunStatus.completed)]
    assert home.branch_updates[0].resume_head == "c-runtime"


class FakeMemoryHome(FakeHome):
    def __init__(self):
        super().__init__()
        self.memories = [{"type": "preference", "content": "Use python3", "tags": ["python"]}]
        self.extractions = []

    def search_memory(self, q, type=None, tags=None):
        del type, tags
        return self.memories if "python" in q.lower() else []

    def create_memory(self, type, content, tags=None, source_session_id="", source_message_ids=None, confidence=1.0):
        del source_session_id, source_message_ids, confidence
        memory = {"type": type, "content": content, "tags": tags or []}
        self.memories.append(memory)
        return memory

    def extract_memory(self, session_id, trigger):
        self.extractions.append((session_id, trigger))
        return {"status": "queued"}


def test_memory_prefetch_injects_matching_memories():
    home = FakeMemoryHome()
    ctx = RunContext(input="python command?", home_client=home)

    MemoryPrefetch(limit=5).run(ctx)

    assert ctx.enhanced_input == (
        "<memory>\n"
        "- [preference] Use python3\n"
        "</memory>\n\n"
        "<user>\n"
        "python command?\n"
        "</user>"
    )


def test_memory_prefetch_falls_back_to_timeline_store_when_home_lacks_memory_search():
    home = FakeHome()
    store = FakeMemoryHome()
    ctx = RunContext(input="python command?", home_client=home, timeline_store=cast(Any, store))

    MemoryPrefetch(limit=5).run(ctx)

    assert ctx.enhanced_input == (
        "<memory>\n"
        "- [preference] Use python3\n"
        "</memory>\n\n"
        "<user>\n"
        "python command?\n"
        "</user>"
    )


def test_memory_prefetch_respects_limit():
    home = FakeMemoryHome()
    home.memories.append({"type": "note", "content": "Use python3 for scripts", "tags": ["python"]})
    ctx = RunContext(input="python command?", home_client=home)

    MemoryPrefetch(limit=1).run(ctx)

    assert ctx.enhanced_input == (
        "<memory>\n"
        "- [preference] Use python3\n"
        "</memory>\n\n"
        "<user>\n"
        "python command?\n"
        "</user>"
    )


def test_memory_command_reports_when_store_does_not_support_memory():
    console = Console(record=True)
    dispatcher = CommandDispatcher(FakeHome(), console)

    asyncio.run(dispatcher.dispatch("/memory search python"))

    assert "Agent-Home memory is not available" in console.export_text()


def test_memory_command_add_search_and_extract_success_paths():
    home = FakeMemoryHome()
    home.memories = []
    console = Console(record=True)
    dispatcher = CommandDispatcher(home, console)
    dispatcher.session_id = "s1"

    asyncio.run(dispatcher.dispatch("/memory add Use python3"))
    asyncio.run(dispatcher.dispatch("/memory search python"))
    asyncio.run(dispatcher.dispatch("/memory extract"))

    output = console.export_text()
    assert home.memories == [{"type": "note", "content": "Use python3", "tags": []}]
    assert home.extractions == [("s1", "manual")]
    assert "Memory added: Use python3" in output
    assert "[note] Use python3" in output


def test_memory_command_missing_arguments_show_usage_before_capability_check():
    console = Console(record=True)
    dispatcher = CommandDispatcher(FakeHome(), console)

    asyncio.run(dispatcher.dispatch("/memory add"))
    asyncio.run(dispatcher.dispatch("/memory search"))

    output = console.export_text()
    assert output.count("Usage: /memory add <content> | /memory search <query> | /memory extract") == 2
    assert "Agent-Home memory is not available" not in output


def test_help_lists_memory_command():
    console = Console(record=True)
    dispatcher = CommandDispatcher(FakeHome(), console)

    asyncio.run(dispatcher.dispatch("/help"))

    assert "/memory" in console.export_text()
