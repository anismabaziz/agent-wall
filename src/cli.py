"""Command-line interface for agent-wall.

Commands:
    evaluate   policy + action -> verdict
    obligations   list obligations (optionally filtered by status)
    audit-log   inspect the audit log
    check   validate a policy file

Run directly (`python main.py ...`) or via the installed `agentwall`
console script (see [project.scripts] in pyproject.toml).
"""
import argparse
import json
from typing import Optional

from src.models import Action, ObligationStatus, load_policy
from src.audit import AuditLogger
from src.engine import PolicyEngine
from src.obligations import ObligationManager
from src.obligation_store import ObligationStore
from src.db import init_db


def _parse_value(raw: str):
	raw = raw.strip()
	lower = raw.lower()
	if lower in ("true", "false"):
		return lower == "true"
	try:
		return int(raw)
	except ValueError:
		pass
	try:
		return float(raw)
	except ValueError:
		pass
	return raw


def _parse_context(items: list[str]) -> dict:
	context = {}
	for item in items:
		if "=" not in item:
			raise argparse.ArgumentTypeError(f"context must be KEY=VALUE, got '{item}'")
		key, value = item.split("=", 1)
		context[key.strip()] = _parse_value(value)
	return context


def _build_engine(policy_file: str) -> tuple[dict, PolicyEngine, ObligationManager]:
	init_db()
	policy = load_policy(policy_file)
	audit_logger = AuditLogger(policy_file=policy_file)
	engine = PolicyEngine(policy, audit_logger=audit_logger)
	manager = ObligationManager(
		poll_interval_seconds=5,
		audit_logger=audit_logger,
		store=ObligationStore(),
	)
	manager.load()
	return {"policy": policy, "audit_logger": audit_logger, "engine": engine, "manager": manager}


def _print_dict(data: dict) -> None:
	print(json.dumps(data, indent=2, default=str))


def cmd_evaluate(args) -> int:
	ctx = _build_engine(args.policy)
	try:
		context = _parse_context(args.context)
	except argparse.ArgumentTypeError as e:
		print(f"error: {e}")
		return 2

	action = Action(
		subject=args.subject,
		action_type=args.action,
		resource=args.resource or "",
		context=context,
	)

	verdict = ctx["engine"].evaluate(action)

	if verdict.decision == "PERMIT" and verdict.obligations:
		ctx["engine"].register_obligations(ctx["manager"], verdict=verdict, subject=args.subject)

	# deterministic ordering: dispensation -> fulfillment -> deadline (issue #16)
	ctx["manager"].enforce(action, ctx["policy"].dispensations, check_deadline=True)

	_print_dict({
		"decision": verdict.decision,
		"explanation": verdict.explanation,
		"obligations": verdict.obligations,
	})
	return 0


def cmd_obligations(args) -> int:
	init_db()
	manager = ObligationManager(
		poll_interval_seconds=5,
		audit_logger=None,
		store=ObligationStore(),
	)
	manager.load()
	status = ObligationStatus(args.status) if args.status else None
	records = manager.get_obligations(status=status)[args.offset:args.offset + args.limit]

	payload = [
		{
			"id": r.id,
			"obligation_id": r.obligation_id,
			"permission_id": r.permission_id,
			"subject": r.subject,
			"obliged_action": r.obliged_action,
			"deadline": r.deadline.isoformat(),
			"status": r.status.value,
			"fulfillment_constraint": r.fulfillment_constraint,
			"fulfilled_at": r.fulfilled_at.isoformat() if r.fulfilled_at else None,
			"violated_at": r.violated_at.isoformat() if r.violated_at else None,
			"waived_at": r.waived_at.isoformat() if r.waived_at else None,
			"waived_by": r.waived_by,
		}
		for r in records
	]
	print(json.dumps(payload, indent=2, default=str))
	return 0


def cmd_audit_log(args) -> int:
	init_db()
	logger = AuditLogger()
	rows = logger.query(limit=args.limit, offset=args.offset)
	print(json.dumps(rows, indent=2, default=str))
	return 0


def cmd_check(args) -> int:
	try:
		policy = load_policy(args.policy)
	except Exception as e:  # noqa: BLE001 - CLI reports any validation failure
		print(f"INVALID: {type(e).__name__}: {e}")
		return 1

	print(
		"OK: "
		f"{len(policy.permissions)} permissions, "
		f"{len(policy.prohibitions)} prohibitions, "
		f"{len(policy.obligations)} obligations, "
		f"{len(policy.dispensations)} dispensations, "
		f"{len(policy.rule_priorities)} rule priorities"
	)
	return 0


def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(prog="agentwall", description="Deontic Policy Firewall CLI")
	sub = parser.add_subparsers(dest="command", required=True)

	p_eval = sub.add_parser("evaluate", help="evaluate an action against a policy")
	p_eval.add_argument("--policy", required=True, help="path to the policy YAML file")
	p_eval.add_argument("--subject", required=True, help="acting subject (agent id)")
	p_eval.add_argument("--action", required=True, dest="action", help="action type")
	p_eval.add_argument("--resource", default="", help="target resource")
	p_eval.add_argument("--context", action="append", default=[], metavar="KEY=VALUE",
						help="context parameter; repeatable")
	p_eval.set_defaults(func=cmd_evaluate)

	p_obl = sub.add_parser("obligations", help="list obligations")
	p_obl.add_argument("--status", choices=[s.value for s in ObligationStatus])
	p_obl.add_argument("--limit", type=int, default=100)
	p_obl.add_argument("--offset", type=int, default=0)
	p_obl.set_defaults(func=cmd_obligations)

	p_audit = sub.add_parser("audit-log", help="inspect the audit log")
	p_audit.add_argument("--limit", type=int, default=100)
	p_audit.add_argument("--offset", type=int, default=0)
	p_audit.set_defaults(func=cmd_audit_log)

	p_check = sub.add_parser("check", help="validate a policy file")
	p_check.add_argument("--policy", required=True)
	p_check.set_defaults(func=cmd_check)

	return parser


def main(argv: Optional[list[str]] = None) -> int:
	parser = build_parser()
	args = parser.parse_args(argv)
	return args.func(args)


if __name__ == "__main__":
	raise SystemExit(main())