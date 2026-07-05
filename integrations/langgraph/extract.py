from typing import Dict, Any, Optional
from src.models import Action
from langgraph.graph import MessagesState
from config import AgentWallConfig


# action normalization 
def normalize_tool_call(
	tool_name: str,
	tool_input: Dict[str, Any],
	state: MessagesState,
	config: AgentWallConfig,
	agent_id: Optional[str] = None
) -> Action:
	"""
	Extract normalized AgentWall Action from LangGraph tool call

	this is the extract step from the Extract-Evaluate-Apply contract
	it maps that raw tool call to a normalized tuple that the PolicyEngine consumes

	Args:
		tool_name: The name of the tool being invoked
		tool_input: The arguments the llm generated for the tool
		state: The current LangGraph state (it contains messages, metadata)
		config: AgentWall config
		agent_id: Identifier for the calling agent

	Returns:
		Normalized Action tuple for policy Evaluation
	"""
	
	subject = agent_id or config.get("default_subject", "unknown_agent")

	resource = _extract_resource(tool_name, tool_input)

	context: Dict[str, Any] = {}
	context.update(tool_input)
	context["thread_id"] = state.get("configurable", {}).get("thread_id", "unknown")
	context["_message_count"] = len(state.get("messages", []))

	# apply a custom context extractor if configured
	extractors = config.get("context_extractors", {})
	if tool_name in extractors:
		extra_context = extractors[tool_name](tool_name, tool_input, state)
		context.update(extra_context)

	context["_tool_name"] = tool_name

	return Action(
		subject=subject,
		action_type=tool_name,
		resource=resource,
		context=context
	)



def _extract_resource(
	tool_name: str,
	tool_input: Dict[str, Any]
) -> str:
	"""
	Heuristic extraction of resource identifier from tool arguments.
	"""
	
	resource_fields = [
        "resource", "path", "file_path", "url", "endpoint",
        "query", "document_id", "user_id", "email", "to",
        "database", "table", "bucket", "key",
  ]

	for field in resource_fields:
		if field in tool_input:
			return str(tool_input[field])
		
	import hashlib
	input_hash = hashlib.sha256(str(sorted(tool_input.items())).encode()).hexdigest()[:8]
	return f"{tool_name}://{input_hash}"

