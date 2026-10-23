import hashlib
import asyncio
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from dotenv import load_dotenv
from fastapi import HTTPException
from decision_engine import generate_proposals

load_dotenv()
REQUEST_LOCKS = {}

from database import (
    IdempotencyRecord,
    SessionLocal,
    StoredTask,
    initialize_database,
)

BASE_URL = os.getenv(
    "A2A_BASE_URL",
    "http://127.0.0.1:8000/a2a/",
)

INPUT_MODE = "application/vnd.ga5.invoice-claim-batch+json"
PROPOSALS_MODE = "application/vnd.ga5.invoice-action-proposals+json"
RECEIPTS_MODE = "application/vnd.ga5.invoice-action-receipts+json"
RESULTS_MODE = "application/vnd.ga5.invoice-action-results+json"


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_database()
    yield


app = FastAPI(
    title="Invoice Action Agent",
    version="1.0.0",
    lifespan=lifespan,
)

def task_to_dict(task):
    return json.loads(task.task_json)


def error_response(status_code, code, message):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )




def validate_request(request: Request):
    authorization = request.headers.get("authorization", "")
    parts = authorization.split()

    if (
        len(parts) != 2
        or parts[0].lower() != "bearer"
        or not parts[1]
    ):
        return None, error_response(
            401,
            "UNAUTHENTICATED",
            "A valid Bearer token is required.",
        )

    if request.headers.get("a2a-version") != "1.0":
        return None, error_response(
            400,
            "UNSUPPORTED_VERSION",
            "A2A-Version must be 1.0.",
        )

    if request.method == "POST":
        content_type = request.headers.get("content-type", "")
        media_type = content_type.split(";", 1)[0].strip().lower()

        if media_type != "application/a2a+json":
            return None, error_response(
                415,
                "UNSUPPORTED_MEDIA_TYPE",
                "Content-Type must be application/a2a+json.",
            )

    principal = hashlib.sha256(
        parts[1].encode("utf-8")
    ).hexdigest()

    return principal, None



def canonical_hash(value):
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


    
async def handle_continuation(principal, message, results_data):
    message_id = message.get("messageId")
    task_id = message.get("taskId")
    context_id = message.get("contextId")

    if not isinstance(message_id, str) or not message_id:
        return error_response(
            400, "INVALID_ARGUMENT", "A messageId is required."
        )

    if not isinstance(task_id, str) or not task_id:
        return error_response(
            400, "INVALID_ARGUMENT", "A taskId is required."
        )

    if not isinstance(context_id, str) or not context_id:
        return error_response(
            400, "INVALID_ARGUMENT", "A contextId is required."
        )

    batch_id = results_data.get("batchId")
    results = results_data.get("results")

    if not isinstance(batch_id, str) or not isinstance(results, list):
        return error_response(
            400, "INVALID_ARGUMENT",
            "A batchId and results list are required."
        )

    message_hash = canonical_hash(message)

    async with SessionLocal() as session:
        async with session.begin():
            replay_query = await session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.principal == principal,
                    IdempotencyRecord.message_id == message_id,
                )
            )
            replay_record = replay_query.scalar_one_or_none()

            if replay_record is not None:
                if replay_record.message_hash != message_hash:
                    return error_response(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "This messageId was already used with different content.",
                    )

                replay_task_query = await session.execute(
                    select(StoredTask).where(
                        StoredTask.id == replay_record.task_id,
                        StoredTask.principal == principal,
                    )
                )
                replay_task = replay_task_query.scalar_one_or_none()

                if replay_task is None:
                    return error_response(
                        500,
                        "TASK_STORAGE_ERROR",
                        "The stored task could not be retrieved.",
                    )

                return {"task": task_to_dict(replay_task)}
        
            query = await session.execute(
                select(StoredTask)
                .where(
                    StoredTask.id == task_id,
                    StoredTask.principal == principal,
                )
                .with_for_update()
            )
            record = query.scalar_one_or_none()

            if record is None:
                return error_response(
                    404, "TASK_NOT_FOUND", "Task not found."
                )

            task = task_to_dict(record)

            if record.context_id != context_id:
                return error_response(
                    409, "CONTEXT_MISMATCH", "The contextId does not match."
                )

            if record.batch_id != batch_id:
                return error_response(
                    409, "BATCH_MISMATCH", "The batchId does not match."
                )

            if task.get("status", {}).get("state") != (
                "TASK_STATE_INPUT_REQUIRED"
            ):
                return error_response(
                    409, "TASK_NOT_CONTINUABLE",
                    "The task is not waiting for a continuation."
                )

            proposal_artifacts = [
                artifact
                for artifact in task.get("artifacts", [])
                for part in artifact.get("parts", [])
                if part.get("mediaType") == PROPOSALS_MODE
            ]

            if len(proposal_artifacts) != 1:
                return error_response(
                    500, "TASK_STORAGE_ERROR",
                    "The task does not contain exactly one proposal artifact."
                )

            proposal_data = proposal_artifacts[0]["parts"][0]["data"]
            proposals = proposal_data.get("proposals", [])

            if not isinstance(results, list) or len(results) != len(proposals):
                return error_response(
                    400, "INVALID_RESULTS",
                    "Exactly one result is required for each proposal."
                )

            proposals_by_package = {
                proposal["packageId"]: proposal for proposal in proposals
            }

            if len(proposals_by_package) != len(proposals):
                return error_response(
                    500, "TASK_STORAGE_ERROR",
                    "The stored proposals contain duplicate package IDs."
                )

            seen_packages = set()
            executions = []

            for result in results:
                if not isinstance(result, dict):
                    return error_response(
                        400, "INVALID_RESULTS",
                        "Every result must be an object."
                    )

                package_id = result.get("packageId")
                action = result.get("action")
                action_id = result.get("actionId")
                outcome = result.get("outcome")
                nonce = result.get("receiptNonce")

                if (
                    not isinstance(package_id, str)
                    or package_id not in proposals_by_package
                    or package_id in seen_packages
                ):
                    return error_response(
                        400, "INVALID_RESULTS",
                        "A result has a missing, unknown, or duplicate packageId."
                    )

                proposal = proposals_by_package[package_id]

                if (
                    action != proposal.get("action")
                    or action_id != proposal.get("actionId")
                ):
                    return error_response(
                        409, "PROPOSAL_MISMATCH",
                        "The result does not match the stored proposal."
                    )

                if outcome not in ("ACCEPTED", "REJECTED"):
                    return error_response(
                        400, "INVALID_RESULTS",
                        "Outcome must be ACCEPTED or REJECTED."
                    )

                if not isinstance(nonce, str) or not nonce.strip():
                    return error_response(
                        400, "INVALID_RESULTS",
                        "A non-empty receiptNonce is required."
                    )

                seen_packages.add(package_id)

                if outcome == "ACCEPTED":
                    executions.append({
                        "packageId": package_id,
                        "actionId": action_id,
                        "action": action,
                        "receiptNonce": nonce,
                        "facts": proposal["facts"],
                        "evidenceRefs": proposal["evidenceRefs"],
                    })

            session.add(
                IdempotencyRecord(
                    principal=principal,
                    message_id=message_id,
                    message_hash=message_hash,
                    task_id=task_id,
                )
            )
                    
            task["history"].append(message)
            task["status"] = {"state": "TASK_STATE_COMPLETED"}
            task["artifacts"].append({
                "artifactId": str(uuid.uuid4()),
                "parts": [{
                    "mediaType": RECEIPTS_MODE,
                    "data": {
                        "batchId": batch_id,
                        "executions": executions,
                    },
                }],
            })

            record.state = "TASK_STATE_COMPLETED"
            record.task_json = json.dumps(
                task,
                separators=(",", ":"),
                ensure_ascii=False,
            )

    return {"task": task}


@app.get("/")
async def health():
    return {"status": "ok", "service": "invoice-action-agent"}


@app.get("/.well-known/agent-card.json")
async def agent_card():
    return {
        "name": "Invoice Action Agent",
        "description": (
            "Analyzes invoice packages, proposes evidence-based "
            "business actions, and executes only accepted actions."
        ),
        "version": "1.0.0",
        "capabilities": {},
        "supportedInterfaces": [
            {
                "url": BASE_URL,
                "protocolBinding": "HTTP+JSON",
                "protocolVersion": "1.0",
            }
        ],
        "defaultInputModes": [INPUT_MODE],
        "defaultOutputModes": [PROPOSALS_MODE, RECEIPTS_MODE],
        "skills": [
            {
                "id": "invoice_action_agent",
                "name": "Invoice Action Agent",
                "description": (
                    "Reconciles invoice evidence and proposes "
                    "safe actions subject to delegated authority."
                ),
                "tags": [
                    "invoices",
                    "reconciliation",
                    "approval",
                    "evidence",
                ],
            }
        ],
    }



@app.post("/a2a/message:send")
async def send_message(request: Request):
    principal, error = validate_request(request)
    if error:
        return error

    try:
        body = await request.json()
    except Exception:
        return error_response(
            400, "INVALID_ARGUMENT", "The request body must be valid JSON."
        )

    message = body.get("message")

    if not isinstance(message, dict):
        return error_response(
            400, "INVALID_ARGUMENT", "A message object is required."
        )

    message_id = message.get("messageId")

    if not isinstance(message_id, str) or not message_id:
        return error_response(
            400, "INVALID_ARGUMENT", "A messageId is required."
        )

    if message.get("role") != "ROLE_USER":
        return error_response(
            400, "INVALID_ARGUMENT", "The message role must be ROLE_USER."
        )

    parts = message.get("parts")

    if not isinstance(parts, list):
        return error_response(
            400, "INVALID_ARGUMENT", "Message parts are required."
        )

    for part in parts:
        if (
           isinstance(part, dict)
           and part.get("mediaType") == RESULTS_MODE
           and isinstance(part.get("data"), dict)
        ):
            return await handle_continuation(
            principal,
            message,
            part["data"],
        )

    batch = None

    for part in parts:
        if (
            isinstance(part, dict)
            and part.get("mediaType") == INPUT_MODE
            and isinstance(part.get("data"), dict)
        ):
            batch = part["data"]
            break

    if batch is None:
        return error_response(
            400,
            "INVALID_ARGUMENT",
            "An invoice claim batch data part is required.",
        )

    batch_id = batch.get("batchId")

    if not isinstance(batch_id, str) or not batch_id:
        return error_response(
            400, "INVALID_ARGUMENT", "A batchId is required."
        )

    message_hash = canonical_hash(message)
    lock_key = (principal, message_id)
    lock = REQUEST_LOCKS.setdefault(lock_key, asyncio.Lock())
    async with lock:
        async with SessionLocal() as session:
            existing_result = await session.execute(
                select(IdempotencyRecord).where(
                    IdempotencyRecord.principal == principal,
                    IdempotencyRecord.message_id == message_id,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing is not None:
                if existing.message_hash != message_hash:
                    return error_response(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "This messageId was already used with different content.",
                    )

                task_result = await session.execute(
                    select(StoredTask).where(
                        StoredTask.id == existing.task_id,
                        StoredTask.principal == principal,
                    )
                )
                stored_task = task_result.scalar_one_or_none()

                if stored_task is None:
                    return error_response(
                        500,
                        "TASK_STORAGE_ERROR",
                        "The stored task could not be retrieved.",
                    )

                return {"task": task_to_dict(stored_task)}

        try:
            proposal_data = await generate_proposals(batch)
            print(f"AI MODEL CALL: principal={principal}, messageId={message_id}")
        except (ValueError, KeyError) as exc:
            print("Proposal validation error:", repr(exc))
            return error_response(
            422,
            "INVALID_PROPOSALS",
            "The invoice batch could not produce valid proposals.",
            )
        except Exception:
            return error_response(
                502,
                "MODEL_ERROR",
                "The invoice decision service failed.",
            )

        now = datetime.now(timezone.utc).isoformat()
        task_id = str(uuid.uuid4())
        context_id = message.get("contextId") or str(uuid.uuid4())

        proposals = proposal_data["proposals"]

        task = {
            "id": task_id,
            "contextId": context_id,
            "status": {
                "state": "TASK_STATE_INPUT_REQUIRED"
            },
            "artifacts": [
                {
                    "artifactId": str(uuid.uuid4()),
                    "parts": [
                        {
                            "mediaType": PROPOSALS_MODE,
                            "data": {
                                "batchId": batch_id,
                                "proposals": proposals,
                            },
                        }
                    ],
                }
            ],
            "history": [message],
        }

        async with SessionLocal() as session:
            try:
                async with session.begin():
                    stored_task = StoredTask(
                        id=task_id,
                        principal=principal,
                        context_id=context_id,
                        batch_id=batch_id,
                        state="TASK_STATE_INPUT_REQUIRED",
                        task_json=json.dumps(
                            task,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ),
                        created_at=now,
                    )

                    idempotency = IdempotencyRecord(
                        principal=principal,
                        message_id=message_id,
                        message_hash=message_hash,
                        task_id=task_id,
                    )

                    session.add(stored_task)
                    session.add(idempotency)
                    await session.flush()

            
            except IntegrityError as exc:
                print("Task storage integrity error:", repr(exc))

                existing_result = await session.execute(
                    select(IdempotencyRecord).where(
                        IdempotencyRecord.principal == principal,
                        IdempotencyRecord.message_id == message_id,
                    )
                )
                existing = existing_result.scalar_one_or_none()

                if existing is not None:
                    if existing.message_hash != message_hash:
                        return error_response(
                            409,
                            "IDEMPOTENCY_CONFLICT",
                            "This messageId was already used with different content.",
                        )

                    task_result = await session.execute(
                        select(StoredTask).where(
                            StoredTask.id == existing.task_id,
                            StoredTask.principal == principal,
                        )
                    )
                    stored_task = task_result.scalar_one_or_none()

                    if stored_task is not None:
                        return {"task": task_to_dict(stored_task)}

                return error_response(
                    500,
                    "TASK_STORAGE_ERROR",
                    "The task could not be saved.",
                )

            except Exception as exc:
                print("Task storage error:", repr(exc))
                return error_response(
                    500,
                    "TASK_STORAGE_ERROR",
                    "The task could not be saved.",
                )


        return {"task": task}



@app.get("/a2a/tasks")
async def list_tasks(request: Request):
    principal, error = validate_request(request)
    if error:
        return error

    async with SessionLocal() as session:
        result = await session.execute(
            select(StoredTask)
            .where(StoredTask.principal == principal)
            .order_by(StoredTask.created_at)
        )
        records = result.scalars().all()

    return {"tasks": [task_to_dict(record) for record in records]}


@app.get("/a2a/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    principal, error = validate_request(request)
    if error:
        return error

    async with SessionLocal() as session:
        result = await session.execute(
            select(StoredTask).where(
                StoredTask.id == task_id,
                StoredTask.principal == principal,
            )
        )
        record = result.scalar_one_or_none()

    if record is None:
        return error_response(404, "TASK_NOT_FOUND", "Task not found.")

    return task_to_dict(record)


@app.post("/a2a/tasks/{task_id}:cancel")
async def cancel_task(task_id: str, request: Request):
    principal, error = validate_request(request)
    if error:
        return error

    async with SessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(StoredTask)
                .where(
                    StoredTask.id == task_id,
                    StoredTask.principal == principal,
                )
                .with_for_update()
            )
            record = result.scalar_one_or_none()

            if record is None:
                return error_response(
                    404, "TASK_NOT_FOUND", "Task not found."
                )

            task = task_to_dict(record)
            state = task.get("status", {}).get("state")

            if state in ("TASK_STATE_COMPLETED", "TASK_STATE_CANCELED"):
                return error_response(
                    409, "TASK_TERMINAL", "Task is already terminal."
                )

            task["status"] = {"state": "TASK_STATE_CANCELED"}
            record.state = "TASK_STATE_CANCELED"
            record.task_json = json.dumps(
                task, separators=(",", ":"), ensure_ascii=False
            )

    return task
