
import httpx

BASE_URL = "http://127.0.0.1:8000/a2a"

HEADERS = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

response = httpx.get(
    f"{BASE_URL}/tasks",
    headers=HEADERS,
    timeout=15,
)
response.raise_for_status()

tasks = response.json()["tasks"]

if not tasks:
    raise SystemExit(
        "No tasks found. Run test_invoice_request.py successfully first."
    )

task = next(
    (
        item for item in tasks
        if item["status"]["state"] == "TASK_STATE_INPUT_REQUIRED"
    ),
    None,
)

if task is None:
    raise SystemExit(
        "No task waiting for continuation was found. "
        "Run test_invoice_request.py to create a new task."
    )

task_id = task["id"]

cancel_response = httpx.post(
    f"{BASE_URL}/tasks/{task_id}:cancel",
    headers=HEADERS,
    json={},
    timeout=15,
)

print("Cancellation status:", cancel_response.status_code)
print("Cancellation response:", cancel_response.text)

if cancel_response.status_code != 200:
    raise SystemExit("Cancellation failed.")

print(
    "Canceled state:",
    cancel_response.json()["status"]["state"],
)

second_response = httpx.post(
    f"{BASE_URL}/tasks/{task_id}:cancel",
    headers=HEADERS,
    json={},
    timeout=15,
)

print("Second cancellation status:", second_response.status_code)
print("Second cancellation response:", second_response.text)
