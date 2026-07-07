from typing import Callable, Sequence, Union, Dict, Any, List, Optional
from langchain_core.tools import BaseTool
from langchain_core.messages import ToolMessage
from langgraph.graph import MessagesState
from .config import AgentWallConfig
from .extract import normalize_tool_call
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from src.audit import AuditLogger
from src.models import Action, Verdict, Obligation
import logging


logger = logging.getLogger(__name__)


class AgentWallToolNode:
	"""
	Drop-in replacement for LangGraphs ToolNode with policy enforcement.

	Follows Extract-Evaluate-Apply contract:
	- Extract: normalize_tool_call() maps raw tool call to an Action tuple
	- Evaluate: PolicyEngine.evaluate() returns a Verdict
	- Apply: execute tool (PERMIT), return violation (PROHIBIT/DEFAULT_DENY)


	"""


	def __init__(
		self,
		tools: Sequence[Union[BaseTool, Callable]],
		policy_engine: PolicyEngine,
		obligation_manager: ObligationManager,
		audit_logger: AuditLogger,
		config: AgentWallConfig
	):
		self.tools = tools
		self.policy_engine = policy_engine
		self.obligation_manager = obligation_manager
		self.audit_logger = audit_logger
		self.config = config


		self.tools_by_name = {
			tool.name: tool for tool in tools
		}

	def __call__(self, state: MessagesState) -> Dict[str, Any]:
		"""
		Execute tool calls with policy enforcement.

		This is the node function that langgraph calls. it:
			Extracts tool calls from the last AIMessage
			For each tool call: Extract -> Evaluate -> Apply
			Returns ToolMessages or policy validation messages
		
		"""
		messages = state.get("messages", [])
		if not messages:
			return {"messages": []}
		
		last_message = messages[-1]

		tool_calls = getattr(last_message, "tool_calls", None)
		if not tool_calls:
			return {"messages": []}
		
		results: List[ToolMessage] = []
		
		for call in tool_calls:
			tool_name = call.get("name") or call.get("function", {}).get("name")
			tool_input = call.get("args") or call.get("function", {}).get("arguments", {})
			tool_call_id = call.get("id", "unknown")

			# extract
			action = normalize_tool_call(
				tool_name=tool_name,
				tool_input=tool_input,
				state=state,
				config=self.config
			)

			# evaluate
			verdict = self.policy_engine.evaluate(action)


			# apply
			if verdict.decision == "PERMIT":
				# check if tool is known
				if tool_name not in self.tools_by_name:
					results.append(
						ToolMessage(
							content=f"Error: Unknown tool '{tool_name}'",
							tool_call_id=tool_call_id
						)
					)
					continue

				# execute tool
				try:
					tool = self.tools_by_name[tool_name]
					result = tool.invoke(tool_input)

					# register obligations
					for obl_id in verdict.obligations:
						self._register_obligation(obl_id, action, verdict)
					
					# check if any action fulfills a pending obligation
					self._check_fulfillement(action)

					results.append(
						ToolMessage(
							content=str(result),
							tool_call_id=tool_call_id
						)
					)
				except Exception as e:
					logger.error(f"Tool execution error for {tool_name}: {e}")

					results.append(
						ToolMessage(
							content=f"Tool execution error: {e}",
							tool_call_id=tool_call_id
						)
					)
			elif verdict.decision == "PROHIBIT":
				# hard block and return a violation message to the agent
				violation_msg = (
					f"POLICY VIOLATION: Action '{tool_name}' is prohibited."
					f"Reason: {verdict.explanation}"
				)
				logger.warning(f"Blocked prohibited action: '{tool_name}' by '{action.subject}'")
				results.append(
					ToolMessage(
						content=violation_msg,
						tool_call_id=tool_call_id
					)
				)
			else: # DEFAULT_DENY
				deny_msg = (
					f"POLICY VIOLATION: Action '{tool_name}' is not explicitly permitted."
					f"Reason: {verdict.explanation}"
				)
				logger.warning(f"Default-denied action: {tool_name} by {action.subject}")
				results.append(
					ToolMessage(
            content=deny_msg,
            tool_call_id=tool_call_id
					)
				)
		
		return {"messages": results}
	

	def _register_obligation(
		self,
		obligation_id: str,
		action: Action,
		verdict: Verdict
	):
		"""
		Register an obligation that rises from a permitted action.
		Looks up the obligation template from the policy engine and created a runtime ObligationRecord
		via the ObligationManager
		"""

		# get obligation from policy engine loaded policy set
		obligation = self._get_obligation_template(obligation_id)

		if not obligation:
			logger.warning(f"Obligation '{obligation_id}' not found in policy")
			return
		
		# extract permission ID that triggers this obligation
		permission_id = self._extract_permission_id(verdict.explanation)

		self.obligation_manager.register(
			obligation_id=obligation_id,
			permission_id=permission_id,
			subject=action.subject,
			obliged_action=obligation.obliged_action,
			deadline_minutes=obligation.deadline_minutes,
			fulfillment_constraint=action.context
		)

		logger.info(f"Registered obligation {obligation_id} for {action.subject}")


	def _check_fulfillement(
		self,
		action: Action
	):
		"""
		Check if the current action fulfills any pending obligations.
		"""

		fulfilled = self.obligation_manager.check_fulfillment(action)

		if fulfilled:
			logger.info(f"Obligation {fulfilled.obligation_id} fulfilled by {action.subject}")


	def _get_obligation_template(
		self,
		obligation_id: str
	) -> Optional[Obligation]:
		"""
		Look up an obligation template from the loaded policy set.
		"""

		for obligation in self.policy_engine.policy_set.obligations:
			if obligation.id == obligation_id:
				return obligation;

		return None
	
	def _extract_permission_id(
		self,
		explanation: str
	):
		"""
		Extract permission id from verdict explanation.
		"""

		if "Permitted by rules: " in explanation:
			return explanation.split("Permitted by rules: ")[1].split(",")[0].strip()
		
		if " outranks " in explanation:
			return explanation.split(": ")[1].split(" ")[0].strip()
		
		return "unknown"









