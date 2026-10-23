
import httpx

BASE_URL = "http://127.0.0.1:8000/a2a"

OWNER_HEADERS = {
    "Authorization": "Bearer local-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

OTHER_HEADERS = {
    "Authorization": "Bearer different-test-token",
    "A2A-Version": "1.0",
    "Content-Type": "application/a2a+json",
}

response = httpx.get(
    f"{BASE_URL}/tasks",
    headers=OWNER_HEADERS,
    timeout=15,
)
response.raise_for_status()

tasks_response = response.json()
print("Task list response:", tasks_response)

if isinstance(tasks_response, dict):
    tasks = tasks_response.get("tasks", [])
elif isinstance(tasks_response, list):
    tasks = tasks_response
else:
    raise SystemExit("Unexpected task-list response format.")

if not tasks:
    raise SystemExit("No tasks found for the owner token.")

task_id = tasks[0]["id"]

other_response = httpx.get(
    f"{BASE_URL}/tasks/{task_id}",
    headers=OTHER_HEADERS,
    timeout=15,
)

print("Other principal task status:", other_response.status_code)
print("Other principal response:", other_response.text)

other_list_response = httpx.get(
    f"{BASE_URL}/tasks",
    headers=OTHER_HEADERS,
    timeout=15,
)

print("Other principal list status:", other_list_response.status_code)
print("Other principal task list:", other_list_response.text)
