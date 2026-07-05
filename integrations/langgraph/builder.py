from typing import Union, Sequence, Callable, Any, Optional, Dict
from langchain_core.tools import BaseTool
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from src.audit import AuditLogger
from config import AgentWallConfig
from tool_node import AgentWallToolNode
from langgraph.graph import MessagesState, StateGraph, START
from langgraph.prebuilt import tools_condition


def build_agent_wall_agent(
	tools: Sequence[Union[BaseTool, Callable]],
	llm: Any,
	policy_engine: PolicyEngine,
	obligation_manager: ObligationManager,
	audit_logger: AuditLogger,
	config: AgentWallConfig,
	checkpointer: Optional[Any] = None
):
	"""
	Build a complete langGraph agent with AgentWall policy enforcement.
	
	this is a convenience function that wires up the standard ReAct pattern with AgentWall policy enforcement
	at the tool boundary

	Args:
		tools: List of LangChain tool
		llm: A langchain chat model with tool bounds
		policy_engine: Initialized PolicyEngine
		obligation_manager: Initialized ObligationManager
		audit_logger: Initialized AuditLogger
		config: AgentWall configuration
		checkpointer: Optional LangGraph checkpointer for persistence

	Returns:
		Compiled LangGraph StateGraph
	"""

	agent_wall_tools = AgentWallToolNode(
		tools=tools,
		policy_engine=policy_engine,
		obligation_manager=obligation_manager,
		audit_logger=audit_logger,
		config=config
	)

	graph = StateGraph(MessagesState)

	def agent_node(state: MessagesState) -> Dict[str, Any]:
		response = llm.invoke(state["messages"])
		return {"messages": [response]}
	
	graph.add_node("agent", agent_node)
	graph.add_node("tools", agent_wall_tools)

	graph.add_edge(START, "agent")
	graph.add_conditional_edges("agent", tools_condition)
	graph.add_edge("tools", "agent")

	return graph.compile(checkpointer=checkpointer)




