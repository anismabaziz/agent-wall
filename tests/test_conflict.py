import pytest
from src.models import RulePriority
from src.conflict import ConflictResolver


def test_conflict_resolver_direct_priority():

	priorities = [
		RulePriority(
        id="PriorityApprovalOverProh",
        greater="Perm_ExportWithApproval",
        lesser="Proh_ExportPII"
		)
	]

	resolver = ConflictResolver(priorities)

	result = resolver.resolve(
		permission_ids=["Perm_ExportWithApproval"],
		prohibition_ids=["Proh_ExportPII"]
	)

	assert result is not None
	winning_id, priority_id = result

	assert winning_id == "Perm_ExportWithApproval"
	assert priority_id == "PriorityApprovalOverProh"



def test_conflict_resolver_no_priority():

	priorities = [
		RulePriority(
			id="PriorityApprovalOverProh",
      greater="Perm_ExportWithApproval",
      lesser="Proh_ExportPII"
		)
	]

	resolver = ConflictResolver(priorities)

	result = resolver.resolve(
		permission_ids=["Perm_ExportWithManagerApproval"],
		prohibition_ids=["Proh_ExportPII"]
	)

	assert result is None



def test_conflict_resolver_prohibition_wins():

	priorities = [
		RulePriority(
			id="PriorityEmergencyLockdown",
			greater="Proh_AllExports",
      lesser="Perm_ManagerOverride"
		)
	]

	resolver = ConflictResolver(priorities)

	result = resolver.resolve(
		permission_ids=["Perm_ManagerOverride"], 
		prohibition_ids=["Proh_AllExports"]
	)

	assert result is not None
	winning_id, priority_id = result
	assert winning_id == "Proh_AllExports"
	assert priority_id == "PriorityEmergencyLockdown"



def test_conflict_resolver_multiple_permissions_one_priority():

	priorities = [
    RulePriority(
      id="PriorityApprovalOverProh",
      greater="Perm_ExportWithApproval",
      lesser="Proh_ExportPII"
    )
  ]

	resolver = ConflictResolver(priorities)

	result = resolver.resolve(
		permission_ids=[
			"Perm_ExportWithApproval",
			"Perm_ExportWithManagerApproval"
		],
		prohibition_ids=["Proh_ExportPII"]
	)

	assert result is not None
	winning_id, priority_id = result
	assert winning_id == "Perm_ExportWithApproval"
	assert priority_id == "PriorityApprovalOverProh"


