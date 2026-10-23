
import json
import uuid
import httpx

BASE_URL = "http://127.0.0.1:8000/a2a"
HEADERS = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

# First, create a task using the existing initial-request test data.
from test_data import request_body

initial_response = httpx.post(
    f"{BASE_URL}/message:send",
    headers=HEADERS,
    json=request_body,
    timeout=45,
)
print("Initial HTTP status:", initial_response.status_code)
print("Initial response:", initial_response.text)

if initial_response.status_code != 200:
    raise SystemExit("Initial request failed. See the response above.")

task = initial_response.json()["task"]

proposal_part = task["artifacts"][0]["parts"][0]["data"]
proposal = proposal_part["proposals"][0]

continuation = {
    "message": {
        "messageId": str(uuid.uuid4()),
        "taskId": task["id"],
        "contextId": task["contextId"],
        "role": "ROLE_USER",
        "parts": [
            {
                "mediaType": "application/vnd.ga5.invoice-action-results+json",
                "data": {
                    "batchId": proposal_part["batchId"],
                    "results": [
                        {
                            "packageId": proposal["packageId"],
                            "actionId": proposal["actionId"],
                            "action": proposal["action"],
                            "outcome": "REJECTED",
                            "receiptNonce": "test-nonce-rejected-001",
                        }
                    ],
                },
            }
        ],
    }
}

response = httpx.post(
    f"{BASE_URL}/message:send",
    headers=HEADERS,
    json=continuation,
    timeout=45,
)

print("Continuation HTTP status:", response.status_code)
print("Continuation response:", response.text)

response.raise_for_status()
completed_task = response.json()["task"]

print("Final state:", completed_task["status"]["state"])
print("Artifact count:", len(completed_task["artifacts"]))

replay_response = httpx.post(
    f"{BASE_URL}/message:send",
    headers=HEADERS,
    json=continuation,
    timeout=45,
)

print("Continuation replay status:", replay_response.status_code)
replay_response.raise_for_status()

replayed_task = replay_response.json()["task"]

print("Same task after replay:", completed_task == replayed_task)
print("Artifact count after replay:", len(replayed_task["artifacts"]))
print("History count after replay:", len(replayed_task["history"]))
