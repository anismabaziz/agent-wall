from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq

from langgraph.checkpoint.memory import MemorySaver
from src.audit import AuditLogger
from src.engine import PolicyEngine
from src.models import Dispensation, Obligation, OntologyClass, Permission, PolicySet, Prohibition, RulePriority
from src.obligations import ObligationManager

from .builder import build_agent_wall_agent
from .config import AgentWallConfig

load_dotenv()


# define tools
@tool
def execute_payment(amount: float, recipient: str, currency: str = "USD", is_cross_border: bool = False,
					approval_credential: dict | None = None) -> str:
	"""
	Execute a payment to a recipient. `is_cross_border` classifies the
	transaction type; an optional `approval_credential` is an operator-verified
	token carrying an `issuer`, never a model-declared authorisation.
"""
	return f"Payment of {currency} {amount} sent to {recipient}"

@tool
def file_ctr(report_id: str) -> str:
		"""
		File a Currency Transaction Report with FinCEN.
"""
		return f"CTR {report_id} filed successfully"

@tool
def check_balance(account: str) -> str:
		"""
		Check account balance.
"""
		return f"Balance for {account}: $1,000,000"


tools = [execute_payment, file_ctr, check_balance]


# operator-owned type ontology: makes a CrossBorderTransfer a HighValueTransaction
# classifies the action's resource type from the (operator-written) tool call
def classify_tool(tool_name: str, tool_input: dict, state: dict) -> list[str]:
	if tool_name == "execute_payment":
		if tool_input.get("is_cross_border") and tool_input.get("amount", 0) >= 100000:
			return ["CrossBorderTransfer"]
		return ["LocalTransfer"]
	return []


# operator-owned credential resolver: only surfaces an issuer from an operator-typed
# credential object; absent/untyped credentials resolve to None (=> denial)
def resolve_credential(tool_name: str, tool_input: dict, state: dict) -> str | None:
	cred = tool_input.get("approval_credential")
	if isinstance(cred, dict):
		return cred.get("issuer")
	return None


# create a policy inline (type hierarchy + trusted credential issuer)
policy = PolicySet(
	ontology=[
		OntologyClass(id="Transaction", subClassOf=[]),
		OntologyClass(id="HighValueTransaction", subClassOf=["Transaction"]),
		OntologyClass(id="CrossBorderTransfer", subClassOf=["HighValueTransaction"]),
	],
	credential_authorities=["TreasuryAuthority"],
	permissions=[
			Permission(
					id="Perm_ApprovedHighValue",
					action="execute_payment",
					constraint={"matches_type": "HighValueTransaction", "credential": "TreasuryAuthority"},
					provisions=["Ob_FileCTR"],
			),
	],
	prohibitions=[
			Prohibition(
					id="Proh_AutoHighValue",
					action="execute_payment",
					constraint={"matches_type": "HighValueTransaction"},
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
  resource_classifier=classify_tool,
  credential_resolver=resolve_credential,
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
	"""
	Run the demo scenarios and print the agent's responses.
"""
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
	"""
	Run the demo and ensure background obligation polling is stopped.
"""
	try:
		run_demo()
	finally:
		obligation_manager.stop()


if __name__ == "__main__":
	main()