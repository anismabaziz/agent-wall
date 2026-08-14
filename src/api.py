from fastapi import FastAPI, Query
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import Optional, List

from src.models import Action, load_policy, ObligationStatus
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from src.obligation_store import ObligationStore
from src.audit import AuditLogger
from src.db import init_db


# global state
POLICY_FILE = "policies/p5_composite.yaml"
policy = load_policy(POLICY_FILE)
audit_logger = AuditLogger(POLICY_FILE)
engine = PolicyEngine(policy_set=policy, audit_logger=audit_logger)
obligation_store = ObligationStore()
obligation_manager = ObligationManager(poll_interval_seconds=10, audit_logger=audit_logger, store=obligation_store)


# start polling on startup
@asynccontextmanager
async def lifespan(app: FastAPI):
	init_db()
	obligation_manager.load()
	obligation_manager.start()
	yield
	obligation_manager.stop()


app = FastAPI(
	title="agent-wall",
	description="Deontic Policy Firewall for Agentic AI",
	lifespan=lifespan,
)


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
		engine.register_obligations(
			obligation_manager,
			verdict=verdict,
			subject=request.subject,
		)
	
	# deterministic ordering: dispensation -> fulfillment -> deadline (issue #16)
	obligation_manager.enforce(action, policy.dispensations, check_deadline=True)

	return EvaluateResponse(
		decision=verdict.decision,
		explanation=verdict.explanation,
		obligations=verdict.obligations
	)



@app.get("/obligations")
async def list_obligations(
	status: Optional[str] = Query(None, enum=["PENDING", "FULFILLED", "VIOLATED", "WAIVED"]),
	limit: int = Query(100, ge=1, le=1000),
	offset: int = Query(0, ge=0),
):
	status_enum = ObligationStatus(status) if status else None
	records = obligation_manager.get_obligations(status=status_enum)[offset:offset + limit]

	return [
		{
			"id": r.id,
			"obligation_id": r.obligation_id,
			"permission_id": r.permission_id,
			"subject": r.subject,
			"obliged_action": r.obliged_action,
			"deadline": r.deadline,
			"status": r.status,
			"fulfillment_constraint": r.fulfillment_constraint,
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

