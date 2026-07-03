from fastapi import FastAPI, Query
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List

from src.models import Action, load_policy, ObligationStatus
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from src.audit import AuditLogger


app = FastAPI(
	title="obligo",
	description="Deontic Policy Firewall for Agentic AI"
)

# global state
POLICY_FILE = "policies/p5_composite.yaml"
policy = load_policy(POLICY_FILE)
audit_logger = AuditLogger(POLICY_FILE)
engine = PolicyEngine(policy_set=policy, audit_logger=audit_logger)
obligation_manager = ObligationManager(poll_interval_seconds=10)

# start polling on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
	obligation_manager.start()
	yield
	obligation_manager.stop()


class EvaluateRequest(BaseModel):
	subject: str
	action_type: str
	resource: str
	context: dict = {}


class EvaluateResponse(BaseModel):
	decision: str
	explanation: str
	obligations: List[str] = []



@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate(request: EvaluateRequest):
	action = Action(
		subject=request.subject,
		action_type=request.action_type,
		resource=request.resource,
		context=request.context
	)

	verdict = engine.evaluate(action)

	# register obligations if permitted
	if verdict.decision == "PERMIT" and verdict.obligations:
		for obl_id in verdict.obligations:

			obligation = next((o for o in verdict.obligations if o == obl_id), None)

			if obligation:
				obligation_manager.register(
					obligation_id=obl_id,
					permission_id="unknown",
					subject=request.subject,
					obliged_action=obligation,
					deadline_minutes=21400
				)
	
	# check dispensation
	if policy.dispensations:
		obligation_manager.check_dispensation(action, policy.dispensations)

	# check fulfillment
	obligation_manager.check_fulfillment(action)

	return EvaluateResponse(
		decision=verdict.decision,
		explanation=verdict.explanation,
		obligations=verdict.obligations
	)



@app.get("/obligations")
async def list_obligations(status: Optional[str] = Query(None, enum=["PENDING", "FULFILLED", "VIOLATED", "WAIVED"])):
	status_enum = ObligationStatus(status) if status else None
	records = obligation_manager.get_obligations(status=status_enum)

	return [
		{
			"id": r.id,
			"obligation_id": r.obligation_id,
			"subject": r.subject,
			"obliged_action": r.obliged_action,
			"deadline": r.deadline,
			"status": r.status,
			"fulfilled_at": r.fulfilled_at if r.fulfilled_at else None,
			"violated_at": r.violated_at if r.violated_at else None,
			"waived_at": r.waived_at if r.waived_at else None,
			"waived_by": r.waived_by if r.waived_by else None
		}
		for r in records
	]


@app.get("/audit-log")
async def get_audit_log(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
	return audit_logger.query(limit, offset)

