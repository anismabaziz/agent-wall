import os
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.audit import AuditLogger
from src.db import init_db
from src.engine import PolicyEngine
from src.models import Action, ObligationStatus, load_policy
from src.obligation_store import ObligationStore
from src.obligations import ObligationManager
from src.rate_limit import SlidingWindowRateLimiter

# global state
POLICY_FILE = "policies/p5_composite.yaml"
policy = load_policy(POLICY_FILE)
audit_logger = AuditLogger(POLICY_FILE)
engine = PolicyEngine(policy_set=policy, audit_logger=audit_logger)
obligation_store = ObligationStore()
obligation_manager = ObligationManager(poll_interval_seconds=10, audit_logger=audit_logger, store=obligation_store)

# ---------------------------------------------------------------------------
# Security knobs (all optional; see README).
#   AGENT_WALL_API_KEY       -> require the X-API-Key header when set
#   AGENT_WALL_RATE_LIMIT    -> max /evaluate requests per subject per minute
#   AGENT_WALL_CORS_ORIGINS  -> comma-separated allowed origins (default "*")
# ---------------------------------------------------------------------------
API_KEY = os.getenv("AGENT_WALL_API_KEY")
_rate_limit_raw = os.getenv("AGENT_WALL_RATE_LIMIT", "1000")
RATE_LIMIT = int(_rate_limit_raw) if _rate_limit_raw.isdigit() else 1000
CORS_ORIGINS = [o.strip() for o in os.getenv("AGENT_WALL_CORS_ORIGINS", "*").split(",") if o.strip()]
_limiter = SlidingWindowRateLimiter(limit=RATE_LIMIT, window_seconds=60)


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
	"""Reject unauthenticated requests when an API key is configured."""
	if not API_KEY:
		return
	if x_api_key != API_KEY:
		raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _check_rate_limit(subject: str) -> None:
	if RATE_LIMIT > 0 and not _limiter.allow(subject):
		raise HTTPException(status_code=429, detail="Rate limit exceeded for subject")


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

app.add_middleware(
	CORSMiddleware,
	allow_origins=CORS_ORIGINS,
	allow_credentials=CORS_ORIGINS != ["*"],
	allow_methods=["*"],
	allow_headers=["*"],
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



@app.post("/evaluate", response_model=EvaluateResponse, dependencies=[Depends(require_api_key)])
async def evaluate(request: EvaluateRequest):
	action = Action(
		subject=request.subject,
		action_type=request.action_type,
		resource=request.resource,
		context=request.context
	)

	_check_rate_limit(request.subject)

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



@app.get("/obligations", dependencies=[Depends(require_api_key)])
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


@app.get("/audit-log", dependencies=[Depends(require_api_key)])
async def get_audit_log(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
	return audit_logger.query(limit, offset)

