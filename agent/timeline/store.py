from __future__ import annotations

from abc import ABC, abstractmethod

from agent.timeline.models import (
    AgentRun,
    Branch,
    Checkpoint,
    Message,
    RunStatus,
    Session,
)


class TimelineStore(ABC):
    # --- Session ---
    @abstractmethod
    def create_session(self, session: Session) -> None: ...

    @abstractmethod
    def get_session(self, session_id: str) -> Session | None: ...

    @abstractmethod
    def update_session(self, session: Session) -> None: ...

    # --- Branch ---
    @abstractmethod
    def create_branch(self, branch: Branch) -> None: ...

    @abstractmethod
    def get_branch(self, branch_id: str) -> Branch | None: ...

    @abstractmethod
    def update_branch(self, branch: Branch) -> None: ...

    # --- AgentRun ---
    @abstractmethod
    def create_run(self, run: AgentRun) -> None: ...

    @abstractmethod
    def get_run(self, run_id: str) -> AgentRun | None: ...

    @abstractmethod
    def update_run_status(self, run_id: str, status: RunStatus) -> None: ...

    # --- Message ---
    @abstractmethod
    def append_message(self, message: Message) -> None: ...

    @abstractmethod
    def get_messages_by_branch(self, branch_id: str, start: int = 0, end: int | None = None) -> list[Message]: ...

    @abstractmethod
    def get_latest_sequence(self, branch_id: str) -> int: ...

    # --- Checkpoint ---
    @abstractmethod
    def create_checkpoint(self, checkpoint: Checkpoint) -> None: ...

    @abstractmethod
    def get_checkpoint(self, checkpoint_id: str) -> Checkpoint | None: ...

    @abstractmethod
    def get_checkpoints_by_branch(self, branch_id: str) -> list[Checkpoint]: ...

    @abstractmethod
    def get_latest_stable_checkpoint(self, branch_id: str) -> Checkpoint | None: ...

    # --- Query helpers ---
    @abstractmethod
    def get_latest_run_by_branch(self, branch_id: str) -> AgentRun | None: ...
