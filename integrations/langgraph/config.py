from typing import Any, Callable, TypedDict


class AgentWallConfig(TypedDict, total=False):
    """Configuration for the AgentWall-LangGraph integration."""

    policy_file: str
    audit_db_path: str
    obligation_poll_interval: int
    default_subject: str
    context_extractors: dict[str, Callable[..., Any]]