#!/usr/bin/env bash
# One-command demo: build the image, start the API, run the flagship
# high-value payment scenario against it, then stop the container.
set -euo pipefail

docker build -t agent-wall .
docker run -d --rm --name agent-wall-demo -p 8000:8000 agent-wall
trap 'docker stop agent-wall-demo >/dev/null' EXIT

echo "Waiting for the API..."
for _ in $(seq 1 30); do
	curl -sf http://localhost:8000/openapi.json >/dev/null && break
	sleep 1
done

echo
echo "--- Flagship scenario: approved high-value payment (expect PERMIT + CTR obligation) ---"
curl -s -X POST http://localhost:8000/evaluate \
	-H "Content-Type: application/json" \
	-d '{
		"subject": "payments_agent_1",
		"action_type": "execute_payment",
		"resource": "transaction://high-value-001",
		"context": {"_resource_types": ["CrossBorderTransfer"], "_credential_issuer": "TreasuryAuthority"}
	}'
echo
echo
echo "--- Pending obligations ---"
curl -s "http://localhost:8000/obligations?status=PENDING"
echo
