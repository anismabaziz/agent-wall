"""Derived obligations.

An obligation is *derived* when at least one matched permission provisions it.
When several permissions provision the same obligation, it is derived only once
(shared obligations are not duplicated).

This module resolves obligation templates from a set of permissions; the policy
engine uses it to compute the obligations attached to a PERMIT verdict.
"""
from typing import Iterable

from src.models import PolicySet, Obligation, Permission


def derived_obligations(
	policy: PolicySet,
	permission_ids: Iterable[str],
) -> list[Obligation]:
	"""Return the unique obligation templates derived from the given permission ids."""
	allowed = set(permission_ids)

	provision_ids: set[str] = set()
	for permission in policy.permissions:
		if permission.id in allowed:
			provision_ids.update(permission.provisions or [])

	by_id = {o.id: o for o in policy.obligations}
	return [by_id[oid] for oid in provision_ids if oid in by_id]


def deriving_permissions(policy: PolicySet, obligation_id: str) -> list[Permission]:
	"""Return the permissions that provision a given obligation (provenance)."""
	return [p for p in policy.permissions if obligation_id in (p.provisions or [])]