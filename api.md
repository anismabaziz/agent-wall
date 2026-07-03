# Terminal 1: Start server

uvicorn obligo.api:app --reload

# Terminal 2: Test flagship scenario

curl -X POST http://localhost:8000/evaluate \
 -H "Content-Type: application/json" \
 -d '{
"subject": "payments_agent_1",
"action_type": "execute_payment",
"resource": "transaction://high-value-001",
"context": {
"is_high_value": true,
"has_treasury_approval": true
}
}'

# Expected response:

# {

# "decision": "PERMIT",

# "explanation": "Resolved by RulePriority Priority_ApprovalOverProh: Perm_ApprovedHighValue outranks conflicting prohibition(s)",

# "obligations": ["Ob_FileCTR"]

# }

# Check audit log

curl http://localhost:8000/audit-log

# Check obligations

curl http://localhost:8000/obligations?status=PENDING
