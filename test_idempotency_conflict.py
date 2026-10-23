
import copy
import uuid
import httpx

from test_data import request_body

BASE_URL = "http://127.0.0.1:8000/a2a"

HEADERS = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

original_request = copy.deepcopy(request_body)
original_request["message"]["messageId"] = str(uuid.uuid4())
original_request["message"]["contextId"] = str(uuid.uuid4())

first_response = httpx.post(
    f"{BASE_URL}/message:send",
    headers=HEADERS,
    json=original_request,
    timeout=45,
)

print("First request status:", first_response.status_code)
print("First response:", first_response.text)
first_response.raise_for_status()

first_task = first_response.json()["task"]

changed_request = copy.deepcopy(original_request)
changed_request["message"]["parts"][0]["data"]["policyRevision"] = (
    "changed-policy-revision"
)

conflict_response = httpx.post(
    f"{BASE_URL}/message:send",
    headers=HEADERS,
    json=changed_request,
    timeout=45,
)

print("Changed request status:", conflict_response.status_code)
print("Changed request response:", conflict_response.text)

if conflict_response.status_code != 409:
    raise SystemExit("FAIL: Expected HTTP 409 for changed message content.")

error = conflict_response.json().get("error", {})

if error.get("code") != "IDEMPOTENCY_CONFLICT":
    raise SystemExit("FAIL: Expected IDEMPOTENCY_CONFLICT.")

print("PASS: Changed content with the same messageId was rejected.")
