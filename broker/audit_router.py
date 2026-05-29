from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from audit import AuditStore, TOOL_CALL
from revocation import RevocationStore


templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


class ToolCallEvent(BaseModel):
    actor_sub: str | None = None
    actor_username: str | None = None
    session_id: str | None = None
    jti: str | None = None
    audience: str
    scope: str | None = None
    method: str
    path: str
    status: int
    reason: str | None = None


def build_router(store: AuditStore, rev: RevocationStore) -> APIRouter:
    router = APIRouter(tags=["audit"])

    @router.post("/audit/event")
    def ingest_tool_event(event: ToolCallEvent) -> dict:
        rowid = store.record(
            event_type=TOOL_CALL,
            actor_sub=event.actor_sub,
            actor_username=event.actor_username,
            session_id=event.session_id,
            jti=event.jti,
            audience=event.audience,
            scope=event.scope,
            method=event.method,
            path=event.path,
            status=event.status,
            reason=event.reason,
        )
        return {"id": rowid}

    @router.get("/audit/events")
    def list_events(session_id: str | None = None, limit: int = 50) -> dict:
        if session_id:
            return {"events": store.events_for_session(session_id, limit=limit)}
        return {"events": store.all_events(limit=limit)}

    @router.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request, session_id: str | None = None) -> HTMLResponse:
        sessions = store.recent_sessions()
        events = store.events_for_session(session_id) if session_id else store.all_events()
        revoked_ids = rev.list_revoked()
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "sessions": sessions,
                "events": events,
                "selected_session": session_id,
                "selected_revoked": session_id in revoked_ids if session_id else False,
                "revoked_ids": revoked_ids,
                "kill_switch_on": rev.is_kill_switch_on(),
            },
        )

    @router.get("/dashboard/feed", response_class=HTMLResponse)
    def dashboard_feed(request: Request, session_id: str | None = None) -> HTMLResponse:
        events = store.events_for_session(session_id) if session_id else store.all_events()
        return templates.TemplateResponse(
            "_events.html",
            {"request": request, "events": events},
        )

    @router.get("/dashboard/sessions", response_class=HTMLResponse)
    def dashboard_sessions(request: Request) -> HTMLResponse:
        sessions = store.recent_sessions()
        revoked_ids = rev.list_revoked()
        return templates.TemplateResponse(
            "_sessions.html",
            {
                "request": request,
                "sessions": sessions,
                "selected_session": None,
                "revoked_ids": revoked_ids,
            },
        )

    return router
