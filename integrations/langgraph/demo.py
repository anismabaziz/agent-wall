from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langgraph.checkpoint.memory import MemorySaver
from src.models import Obligation, PolicySet, Prohibition, Dispensation, RulePriority, Permission
from src.audit import AuditLogger
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from .config import AgentWallConfig
from .builder import build_agent_wall_agent
from dotenv import load_dotenv
load_dotenv()


# define tools
@tool
def execute_payment(amount: float, recipient: str, currency: str = "USD") -> str:
	"""Execute a payment to a recipient."""
	return f"Payment of {currency} {amount} sent to {recipient}"

@tool
def file_ctr(report_id: str) -> str:
		"""File a Currency Transaction Report with FinCEN."""
		return f"CTR {report_id} filed successfully"

@tool
def check_balance(account: str) -> str:
		"""Check account balance."""
		return f"Balance for {account}: $1,000,000"


tools = [execute_payment, file_ctr, check_balance]


# create a policy inline
policy = PolicySet(
	permissions=[
			Permission(
					id="Perm_ApprovedHighValue",
					action="execute_payment",
					constraint={"is_high_value": True, "has_treasury_approval": True},
					provisions=["Ob_FileCTR"],
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
					deadline_minutes=21600,  # 15 days
					description="File CTR with FinCEN within 15 days",
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


# initialize AgentWall components
audit_logger = AuditLogger(policy_file="demo")
policy_engine = PolicyEngine(policy, audit_logger=audit_logger)
obligation_manager = ObligationManager(poll_interval_seconds=5, audit_logger=audit_logger)
config = AgentWallConfig(
  policy_file="demo",
  default_subject="payments_agent_1",
)

# build agent
llm = ChatGroq(
    model="llama-3.3-70b-versatile",
    temperature=0,
)
llm_with_tools = llm.bind_tools(tools)
app = build_agent_wall_agent(
	tools=tools,
	llm=llm_with_tools,
	policy_engine=policy_engine,
  obligation_manager=obligation_manager,
	audit_logger=audit_logger,
  config=config,
  checkpointer=MemorySaver()
)


# test scenarios
print("=" * 70)
print("AGENTWALL-LANGGRAPH INTEGRATION DEMO")
print("Flagship Policy: Financial Services")
print("=" * 70)


def run_demo() -> None:
	# Scenario 1: Unauthorized high-value payment (should be blocked)
	print("\n--- Scenario 1: Unauthorized High-Value Payment ---")
	result = app.invoke({
		"messages": [
			HumanMessage(
			"Execute a high-value payment of $500,000 to vendor ABC Corp"
			)
		]
	}, 
	config={"configurable": {"thread_id": "scenario-1"}}
	)

	for msg in result["messages"]:
		print(f"  {msg.type}: {msg.content[:200]}")


def main() -> None:
	try:
		run_demo()
	finally:
		obligation_manager.stop()


if __name__ == "__main__":
	main()
