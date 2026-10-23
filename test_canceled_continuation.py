
import uuid
import httpx

from test_data import request_body

BASE_URL = "http://127.0.0.1:8000/a2a"

HEADERS = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

request_body = {
    **request_body,
    "message": {
        **request_body["message"],
        "messageId": str(uuid.uuid4()),
        "contextId": str(uuid.uuid4()),
    },
}

initial_response = httpx.post(
    f"{BASE_URL}/message:send",
    headers=HEADERS,
    json=request_body,
    timeout=45,
)

print("Initial status:", initial_response.status_code)
print("Initial response:", initial_response.text)
initial_response.raise_for_status()

task = initial_response.json()["task"]
proposal_data = task["artifacts"][0]["parts"][0]["data"]
proposal = proposal_data["proposals"][0]

cancel_response = httpx.post(
    f"{BASE_URL}/tasks/{task['id']}:cancel",
    headers=HEADERS,
    json={},
    timeout=15,
)

print("Cancellation status:", cancel_response.status_code)
cancel_response.raise_for_status()

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
                    "batchId": proposal_data["batchId"],
                    "results": [
                        {
                            "packageId": proposal["packageId"],
                            "actionId": proposal["actionId"],
                            "action": proposal["action"],
                            "outcome": "ACCEPTED",
                            "receiptNonce": "test-nonce-canceled-task",
                        }
                    ],
                },
            }
        ],
    }
}

continuation_response = httpx.post(
    f"{BASE_URL}/message:send",
    headers=HEADERS,
    json=continuation,
    timeout=45,
)

print("Continuation after cancellation status:", continuation_response.status_code)
print("Continuation after cancellation response:", continuation_response.text)

task_response = httpx.get(
    f"{BASE_URL}/tasks/{task['id']}",
    headers=HEADERS,
    timeout=15,
)

print("Final task state:", task_response.json()["status"]["state"])
print("Final artifact count:", len(task_response.json()["artifacts"]))
