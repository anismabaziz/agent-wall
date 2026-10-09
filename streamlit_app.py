"""Streamlit frontend for manually testing AgentWall policies.

Run with:
    uv run streamlit run streamlit_app.py

Uses PolicyEngine directly (no FastAPI server needed). Obligations live in
memory per session so testing does not pollute the shared SQLite store,
while decisions are still written to the audit log.
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.audit import AuditLogger
from src.db import init_db
from src.engine import PolicyEngine
from src.models import Action, ObligationStatus, load_policy

REPO_ROOT = Path(__file__).resolve().parent
POLICIES_DIR = REPO_ROOT / "policies"
SCENARIOS_DIR = REPO_ROOT / "scenarios"


st.set_page_config(page_title="AgentWall tester", layout="wide")


def list_policies() -> list[str]:
	files = sorted(POLICIES_DIR.glob("*.yaml"))
	return [str(f.relative_to(REPO_ROOT)) for f in files] or ["policies/p5_composite.yaml"]


def list_scenarios() -> dict[str, Path]:
	if not SCENARIOS_DIR.is_dir():
		return {}
	out = {}
	for f in sorted(SCENARIOS_DIR.glob("*.json")):
		try:
			data = json.loads(f.read_text())
			out[data.get("name", f.name)] = f
		except (OSError, json.JSONDecodeError):
			continue
	return out


def get_engine_context(policy_file: str):
	"""Build (or reuse) engine + manager + audit logger for the session."""
	from src.obligations import ObligationManager as _Manager

	key = f"ctx::{policy_file}"
	if key not in st.session_state or st.session_state.get("active_policy") != policy_file:
		init_db()
		policy = load_policy(policy_file)
		audit_logger = AuditLogger(policy_file)
		engine = PolicyEngine(policy, audit_logger=audit_logger)
		manager = _Manager(poll_interval_seconds=10, audit_logger=audit_logger)
		st.session_state[key] = {
			"policy": policy,
			"engine": engine,
			"manager": manager,
			"audit": audit_logger,
		}
		st.session_state["active_policy"] = policy_file
		st.session_state["history"] = []
	return st.session_state[key]


def parse_context(raw: str) -> tuple[dict, str | None]:
	raw = (raw or "").strip()
	if not raw:
		return {}, None
	try:
		data = json.loads(raw)
	except json.JSONDecodeError as e:
		return {}, f"Invalid JSON: {e}"
	if not isinstance(data, dict):
		return {}, "Context must be a JSON object"
	return data, None


# ---------------------------------------------------------------- sidebar ---
policies = list_policies()
default_idx = policies.index("policies/p5_composite.yaml") if "policies/p5_composite.yaml" in policies else 0

with st.sidebar:
	st.header("Policy")
	policy_file = st.selectbox("Policy file", policies, index=default_idx)
	ctx = get_engine_context(policy_file)
	policy = ctx["policy"]

	st.caption(
		f"{len(policy.permissions)} permissions, "
		f"{len(policy.prohibitions)} prohibitions, "
		f"{len(policy.obligations)} obligations, "
		f"{len(policy.dispensations)} dispensations"
	)
	st.caption(f"Default: {policy.default_behavior}")

	if st.button("Reset session (clear obligations + history)"):
		key = f"ctx::{policy_file}"
		st.session_state.pop(key, None)
		st.session_state.pop("history", None)
		st.rerun()

	st.divider()
	st.header("Scenario preset")
	scenarios = list_scenarios()
	scenario_name = st.selectbox("Scenario", ["(none)"] + list(scenarios.keys()))
	if st.button("Load preset into form", disabled=scenario_name == "(none)"):
		data = json.loads(scenarios[scenario_name].read_text())
		first = (data.get("actions") or [{}])[0]
		st.session_state["f_subject"] = first.get("subject", "")
		st.session_state["f_action"] = first.get("action_type", "")
		st.session_state["f_resource"] = first.get("resource", "")
		st.session_state["f_context"] = json.dumps(first.get("context", {}), indent=2)
		preset_policy = data.get("policy")
		if preset_policy and preset_policy in policies:
			st.warning(f"Preset expects {preset_policy}. Switch the policy selector to match it.")
		st.rerun()

# ------------------------------------------------------------------ tabs ---
st.title("AgentWall tester")
st.caption(f"Testing {policy_file} directly through PolicyEngine. Audit entries go to the shared SQLite log.")

tab_eval, tab_obl, tab_audit, tab_policy = st.tabs(["Evaluate", "Obligations", "Audit log", "Policy"])

with tab_eval:
	col_form, col_result = st.columns([1, 1])

	with col_form:
		st.subheader("Action")
		subject = st.text_input("Subject", value=st.session_state.get("f_subject", "payments_agent_1"))
		action_type = st.text_input("Action type", value=st.session_state.get("f_action", "execute_payment"))
		resource = st.text_input("Resource", value=st.session_state.get("f_resource", "transaction://high-value-001"))
		context_raw = st.text_area(
			"Context (JSON object)",
			value=st.session_state.get(
				"f_context",
				json.dumps(
					{"_resource_types": ["CrossBorderTransfer"], "_credential_issuer": "TreasuryAuthority"},
					indent=2,
				),
			),
			height=200,
		)
		with st.expander("Reserved context keys"):
			st.markdown(
				"`_resource_types` stages ontology types for `matches_type` checks. "
				"`_credential_issuer` must be in `credential_authorities` for `credential` checks. "
				"The model cannot self-authorize; these stand in for operator-owned resolvers."
			)
		run = st.button("Evaluate", type="primary")

	with col_result:
		st.subheader("Verdict")
		if run:
			context, err = parse_context(context_raw)
			if err:
				st.error(err)
			elif not subject or not action_type:
				st.error("Subject and action type are required.")
			else:
				action = Action(subject=subject, action_type=action_type, resource=resource, context=context)
				verdict = ctx["engine"].evaluate(action)
				if verdict.decision == "PERMIT" and verdict.obligations:
					ctx["engine"].register_obligations(ctx["manager"], verdict=verdict, subject=subject)
				outcomes = ctx["manager"].enforce(action, policy.dispensations, check_deadline=True)

				st.session_state["history"].insert(
					0,
					{
						"subject": subject,
						"action": action_type,
						"resource": resource,
						"decision": verdict.decision,
						"explanation": verdict.explanation,
					},
				)

				color = {"PERMIT": "green", "PROHIBIT": "red"}.get(verdict.decision, "orange")
				st.markdown(f":{color}[**{verdict.decision}**]")
				st.write(verdict.explanation)
				if verdict.obligations:
					st.write("Obligations from verdict:", ", ".join(verdict.obligations))
				waived = outcomes.get("dispensation") or []
				fulfilled = outcomes.get("fulfilled")
				if waived:
					st.info(f"Waived: {', '.join(r.obligation_id for r in waived)}")
				if fulfilled is not None:
					st.success(f"Fulfilled obligation: {fulfilled.obligation_id}")

		if st.session_state.get("history"):
			st.divider()
			st.subheader("This session")
			st.dataframe(st.session_state["history"], width="stretch", hide_index=True)

with tab_obl:
	st.subheader("Tracked obligations (in-memory)")
	status_filter = st.selectbox("Status filter", ["ALL"] + [s.value for s in ObligationStatus], key="obl_filter")
	if st.button("Check deadlines now"):
		ctx["manager"]._check_deadlines()
	status = ObligationStatus(status_filter) if status_filter != "ALL" else None
	records = ctx["manager"].get_obligations(status=status)
	rows = [
		{
			"obligation": r.obligation_id,
			"subject": r.subject,
			"obliged_action": r.obliged_action,
			"status": r.status.value if hasattr(r.status, "value") else str(r.status),
			"deadline": r.deadline.isoformat() if r.deadline else None,
			"permission": r.permission_id,
			"waived_by": r.waived_by,
		}
		for r in records
	]
	st.dataframe(rows, width="stretch", hide_index=True)
	st.caption("Tip: fulfill an obligation by evaluating its obliged action (e.g. `file_ctr`) with the same subject.")

with tab_audit:
	st.subheader("Audit log (shared SQLite)")
	limit = st.slider("Entries", 10, 500, 100, key="audit_limit")
	if st.button("Refresh"):
		st.rerun()
	rows = ctx["audit"].query(limit=limit)
	st.dataframe(rows, width="stretch", hide_index=True)

with tab_policy:
	st.subheader("Policy contents")
	cols = st.columns(2)
	with cols[0]:
		st.write("Permissions")
		st.dataframe(
			[{"id": p.id, "action": p.action, "constraint": json.dumps(p.constraint)} for p in policy.permissions],
			width="stretch",
			hide_index=True,
		)
		st.write("Prohibitions")
		st.dataframe(
			[{"id": p.id, "action": p.action, "constraint": json.dumps(p.constraint)} for p in policy.prohibitions],
			width="stretch",
			hide_index=True,
		)
	with cols[1]:
		st.write("Obligations")
		st.dataframe(
			[
				{"id": o.id, "obliged_action": o.obliged_action, "deadline_min": o.deadline_minutes}
				for o in policy.obligations
			],
			width="stretch",
			hide_index=True,
		)
		st.write("Dispensations")
		st.dataframe(
			[{"id": d.id, "waives": d.waives, "constraint": json.dumps(d.constraint)} for d in policy.dispensations],
			width="stretch",
			hide_index=True,
		)
	with st.expander("Raw YAML"):
		st.code((REPO_ROOT / policy_file).read_text(), language="yaml")
