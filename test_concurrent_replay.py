
import copy
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx

from test_data import request_body

BASE_URL = "http://127.0.0.1:8000/a2a"
NUMBER_OF_REQUESTS = 5

HEADERS = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

body = copy.deepcopy(request_body)
body["message"]["messageId"] = str(uuid.uuid4())
body["message"]["contextId"] = str(uuid.uuid4())


def send_request(_):
    try:
        response = httpx.post(
            f"{BASE_URL}/message:send",
            headers=HEADERS,
            json=body,
            timeout=45,
        )

        try:
            response_body = response.json()
        except ValueError:
            response_body = {"raw_response": response.text}

        task = response_body.get("task", {})

        return {
            "status": response.status_code,
            "task_id": task.get("id"),
            "body": response_body,
        }

    except Exception as exc:
        return {
            "status": None,
            "task_id": None,
            "body": {"error": repr(exc)},
        }


with ThreadPoolExecutor(max_workers=NUMBER_OF_REQUESTS) as executor:
    results = list(executor.map(send_request, range(NUMBER_OF_REQUESTS)))

for index, result in enumerate(results, start=1):
    print(
        f"Request {index}: status={result['status']}, "
        f"task_id={result['task_id']}"
    )
    if result["status"] != 200:
        print("Response:", result["body"])

successful_results = [
    result for result in results
    if result["status"] == 200 and result["task_id"]
]

task_ids = {
    result["task_id"] for result in successful_results
}

print("Successful responses:", len(successful_results))
print("Distinct task IDs:", len(task_ids))

if len(successful_results) == NUMBER_OF_REQUESTS and len(task_ids) == 1:
    print("PASS: All requests returned the same task.")
else:
    print("FAIL: Concurrent replay behavior needs investigation.")
