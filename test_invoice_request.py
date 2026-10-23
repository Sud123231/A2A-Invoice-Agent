
import json
import uuid

import httpx


message_id = str(uuid.uuid4())
batch_id = str(uuid.uuid4())

batch = {
    "batchId": batch_id,
    "policyRevision": "test-policy-1",
    "packages": [
        {
            "packageId": "test-package-001",
            "documents": [
                {
                    "type": "invoice",
                    "text": (
                        "Invoice from Acme Supplies. "
                        "Invoice number INV-001. "
                        "Amount INR 1,000.00. "
                        "[INV-001]"
                    ),
                },
                {
                    "type": "reconciliation",
                    "text": (
                        "The invoice matches the purchase order and "
                        "goods receipt. The amount is within the "
                        "autonomous approval limit. [MATCH-001]"
                    ),
                },
                {
                    "type": "payment_status",
                    "text": (
                        "No previous payment was found for this "
                        "commercial invoice. [PAY-001]"
                    ),
                },
            ],
        }
    ],
}

request_body = {
    "message": {
        "messageId": message_id,
        "contextId": str(uuid.uuid4()),
        "role": "ROLE_USER",
        "parts": [
            {
                "mediaType": (
                    "application/vnd.ga5.invoice-claim-batch+json"
                ),
                "data": batch,
            }
        ],
    },
    "configuration": {
        "returnImmediately": False,
        "historyLength": 20,
        "acceptedOutputModes": [
            "application/vnd.ga5.invoice-action-proposals+json",
            "application/vnd.ga5.invoice-action-receipts+json",
        ],
    },
}


headers = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

url = "http://127.0.0.1:8000/a2a/message:send"


def send_request():
    return httpx.post(
        url,
        headers=headers,
        content=json.dumps(request_body),
        timeout=45,
    )


first_response = send_request()
print("First HTTP status:", first_response.status_code)
print("First response body:", first_response.text)
first_response.raise_for_status()
first_task = first_response.json()["task"]

second_response = send_request()
print("Replay HTTP status:", second_response.status_code)
second_response.raise_for_status()
second_task = second_response.json()["task"]

print("Same task ID:", first_task["id"] == second_task["id"])
print("Same action ID:", (
    first_task["artifacts"][0]["parts"][0]["data"]["proposals"][0]["actionId"]
    == second_task["artifacts"][0]["parts"][0]["data"]["proposals"][0]["actionId"]
))
print("Same complete task:", first_task == second_task)
