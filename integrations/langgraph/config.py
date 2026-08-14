from typing import Any, Callable, TypedDict


class AgentWallConfig(TypedDict, total=False):
    """
    Configuration for the AgentWall-LangGraph integration.
"""

    policy_file: str
    audit_db_path: str
    obligation_poll_interval: int
    default_subject: str
    context_extractors: dict[str, Callable[..., Any]]
    # operator-owned: derives the action's resource type(s) for `matches_type`
    resource_classifier: Callable[..., Any]
    # operator-owned: resolves a presented credential to a verified issuer
    credential_resolver: Callable[..., Any]