"""Unit tests for the LangGraph enforcement node (Extract-Evaluate-Apply).

These exercise AgentWallToolNode directly with fabricated messages, so no
live LLM or network access is required. See issue #14.
"""
from langchain_core.tools import tool
from langchain_core.messages import AIMessage, ToolMessage

from src.models import (
	Obligation, PolicySet, Prohibition, Dispensation, RulePriority, Permission,
	ObligationStatus,
)
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from integrations.langgraph.config import AgentWallConfig
from integrations.langgraph.tool_node import AgentWallToolNode


@tool
def execute_payment(amount: float, recipient: str, currency: str = "USD") -> str:
	"""Execute a payment to a recipient."""
	return f"Payment of {currency} {amount} sent to {recipient}"


@tool
def file_ctr(report_id: str) -> str:
	"""File a Currency Transaction Report with FinCEN."""
	return f"CTR {report_id} filed successfully"


TOOLS = [execute_payment, file_ctr]


def _policy() -> PolicySet:
	return PolicySet(
		permissions=[
			Permission(
				id="Perm_ApprovedHighValue",
				action="execute_payment",
				constraint={"is_high_value": True, "has_treasury_approval": True},
				provisions=["Ob_FileCTR"],
			),
			Permission(
				id="Perm_FileCTR",
				action="file_ctr",
				constraint={},
			),
		],
		prohibitions=[
			Prohibition(
				id="Proh_AutoHighValue",
				action="execute_payment",
				constraint={"is_high_value": True},
			),
		],
		obligations=[
			Obligation(
				id="Ob_FileCTR",
				obliged_action="file_ctr",
				deadline_minutes=60,
				description="File CTR",
			),
		],
		dispensations=[
			Dispensation(
				id="Disp_ExemptCTR",
				constraint={"is_exempt_counterparty": True},
				waives="Ob_FileCTR",
			),
		],
		rule_priorities=[
			RulePriority(
				id="Priority_ApprovalOverProh",
				greater="Perm_ApprovedHighValue",
				lesser="Proh_AutoHighValue",
			),
		],
		default_behavior="explicit_permit_implicit_prohibit",
	)


def _node() -> tuple[AgentWallToolNode, ObligationManager]:
	engine = PolicyEngine(_policy(), audit_logger=None)
	manager = ObligationManager(poll_interval_seconds=5, audit_logger=None)
	config = AgentWallConfig(default_subject="payments_agent_1")
	node = AgentWallToolNode(
		tools=TOOLS,
		policy_engine=engine,
		obligation_manager=manager,
		audit_logger=None,
		config=config,
	)
	return node, manager


def _invoke(node: AgentWallToolNode, tool_name: str, args: dict) -> list[ToolMessage]:
	msg = AIMessage(content="", tool_calls=[{"name": tool_name, "args": args, "id": "call_1"}])
	state = {
		"messages": [msg],
		"configurable": {"thread_id": "test-thread"},
	}
	return node(state)["messages"]


def _content(results: list[ToolMessage]) -> str:
	return next(r.content for r in results)


def test_permit_executes_tool():
	node, _ = _node()
	results = _invoke(node, "execute_payment", {
		"amount": 500000.0,
		"recipient": "ABC Corp",
		"is_high_value": True,
		"has_treasury_approval": True,
	})
	assert len(results) == 1
	assert "Payment of USD 500000.0 sent to ABC Corp" in _content(results)


def test_prohibit_blocks_with_violation():
	node, _ = _node()
	results = _invoke(node, "execute_payment", {
		"amount": 500000.0,
		"recipient": "ABC Corp",
		"is_high_value": True,  # prohibited without treasury approval
	})
	assert len(results) == 1
	assert "POLICY VIOLATION" in _content(results)
	assert "is prohibited" in _content(results)


def test_default_deny_blocks_unapproved_action():
	node, _ = _node()
	results = _invoke(node, "check_balance", {"account": "123"})
	assert len(results) == 1
	assert "POLICY VIOLATION" in _content(results)
	assert "not explicitly permitted" in _content(results)


def test_unknown_tool_on_permit_path():
	node, manager = _node()
	# any tool is default-denied here (nothing permits check_balance) -> NOT the
	# "unknown tool" branch. Exercise the unknown-tool branch via a permitted
	# action whose tool was never registered.
	node2 = AgentWallToolNode(
		tools=[file_ctr],  # execute_payment NOT in tools
		policy_engine=node.policy_engine,
		obligation_manager=manager,
		audit_logger=None,
		config=AgentWallConfig(default_subject="payments_agent_1"),
	)
	results = _invoke(node2, "execute_payment", {
		"amount": 500000.0,
		"recipient": "ABC Corp",
		"is_high_value": True,
		"has_treasury_approval": True,
	})
	assert len(results) == 1
	assert "Unknown tool" in _content(results)


def test_permitted_action_registers_obligation():
	node, manager = _node()
	_invoke(node, "execute_payment", {
		"amount": 500000.0,
		"recipient": "ABC Corp",
		"is_high_value": True,
		"has_treasury_approval": True,
	})
	records = manager.get_obligations(status=ObligationStatus.PENDING)
	assert len(records) == 1
	assert records[0].obligation_id == "Ob_FileCTR"
	assert records[0].permission_id == "Perm_ApprovedHighValue"


def test_filing_ctr_fulfills_pending_obligation():
	node, manager = _node()
	# Trigger the obligation first.
	_invoke(node, "execute_payment", {
		"amount": 500000.0,
		"recipient": "ABC Corp",
		"is_high_value": True,
		"has_treasury_approval": True,
	})
	pending = [r for r in manager.get_obligations() if r.status == ObligationStatus.PENDING]
	assert len(pending) == 1

	# Filing the CTR fulfills it.
	_invoke(node, "file_ctr", {"report_id": "CTR-001"})
	oblig = next(r for r in manager.get_obligations() if r.obligation_id == "Ob_FileCTR")
	assert oblig.status == ObligationStatus.FULFILLED


def test_empty_messages_returns_empty():
	node, _ = _node()
	assert node({"messages": []}) == {"messages": []}
	assert node({"messages": []}).get("messages") == []