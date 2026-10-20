from fastapi import FastAPI

from app.routers import agent, auth, calendar, deadlines, files, subjects

app = FastAPI(
    title="API учебных документов и дедлайнов",
    version="1.0.0",
    description=(
        "API для загрузки PDF, просмотра результатов фоновой обработки и управления дедлайнами."
    ),
)

app.include_router(auth.router)
app.include_router(subjects.router)
app.include_router(files.router)
app.include_router(deadlines.router)
app.include_router(calendar.router)
app.include_router(agent.router)


@app.get("/health", include_in_schema=False)
def health() -> dict[str, str]:
    return {"status": "ok"}
