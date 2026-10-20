from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from app.db import SessionLocal
from app.models import DocumentFile, Subject
from app.security import CurrentUser, DatabaseSession

router = APIRouter(prefix="/api/agent", tags=["Agent"])


class AgentRunRequest(BaseModel):
    file_id: uuid.UUID
    sync: bool = False


class AgentRunResponse(BaseModel):
    file_id: uuid.UUID
    status: str
    run_id: str | None = None
    iterations: int | None = None
    tool_calls: int | None = None
    deadlines_saved: int | None = None
    summary_saved: bool | None = None
    error: str | None = None


async def _run_agent_background(file_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    from app.agent.agent import process_file
    from app.agent.integration import AsyncSqlAlchemyRepository

    async with SessionLocal() as db:
        repo = AsyncSqlAlchemyRepository(db)
        return await process_file(
            file_id=str(file_id),
            repository=repo,
            owner_id=str(user_id),
        )


@router.post(
    "/run",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=AgentRunResponse,
    operation_id="runAgent",
)
async def run_agent(
    body: AgentRunRequest,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> AgentRunResponse:
    f = await db.scalar(
        select(DocumentFile)
        .join(Subject)
        .where(DocumentFile.id == body.file_id, Subject.user_id == current_user.id)
    )
    if f is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "File not found")

    from app.agent.integration import AsyncSqlAlchemyRepository

    repo = AsyncSqlAlchemyRepository(db)
    await repo.clear_file_results(str(f.id), str(current_user.id))
    await repo.set_file_status(str(f.id), "uploaded", error=None)

    if body.sync:
        result = await _run_agent_background(f.id, current_user.id)
        return AgentRunResponse(
            file_id=f.id,
            status=result.get("status", "failed"),
            run_id=result.get("run_id"),
            iterations=result.get("iterations"),
            tool_calls=result.get("tool_calls"),
            deadlines_saved=result.get("deadlines_saved"),
            summary_saved=result.get("summary_saved"),
            error=result.get("error"),
        )

    background_tasks.add_task(_run_agent_background, f.id, current_user.id)
    return AgentRunResponse(file_id=f.id, status="queued")
