"""HTTP surface for the revocation list and kill switch.

Endpoints are intentionally simple. The dashboard wires HTMX hx-post
buttons to these. A real deployment would gate them behind broker-admin
authentication; for the demo they're open.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from audit import (
    AuditStore,
    KILL_SWITCH_DISENGAGED,
    KILL_SWITCH_ENGAGED,
    SESSION_REVOKED,
    SESSION_UNREVOKED,
)
from revocation import RevocationStore


def build_router(rev: RevocationStore, audit: AuditStore) -> APIRouter:
    router = APIRouter(tags=["revocation"])

    # ---- session revocation ------------------------------------------------

    @router.post("/sessions/{session_id}/revoke", response_model=None)
    def revoke(session_id: str, request: Request) -> HTMLResponse | dict:
        rev.revoke_session(
            session_id,
            revoked_by="dashboard",
            reason="revoked by operator",
        )
        audit.record(
            event_type=SESSION_REVOKED,
            session_id=session_id,
            reason="revoked by operator",
        )
        if _wants_html(request):
            return RedirectResponse(
                url=f"/dashboard?session_id={session_id}", status_code=303
            )
        return {"session_id": session_id, "revoked": True}

    @router.post("/sessions/{session_id}/unrevoke", response_model=None)
    def unrevoke(session_id: str, request: Request) -> HTMLResponse | dict:
        removed = rev.unrevoke_session(session_id)
        if removed:
            audit.record(
                event_type=SESSION_UNREVOKED,
                session_id=session_id,
                reason="unrevoked by operator",
            )
        if _wants_html(request):
            return RedirectResponse(
                url=f"/dashboard?session_id={session_id}", status_code=303
            )
        return {"session_id": session_id, "revoked": False}

    @router.get("/sessions/{session_id}")
    def session_status(session_id: str) -> dict:
        return {
            "session_id": session_id,
            "revoked": rev.is_revoked(session_id),
        }

    # ---- kill switch -------------------------------------------------------

    @router.post("/kill-switch", response_model=None)
    def engage(request: Request) -> HTMLResponse | dict:
        rev.engage_kill_switch()
        audit.record(event_type=KILL_SWITCH_ENGAGED, reason="engaged by operator")
        if _wants_html(request):
            return RedirectResponse(url="/dashboard", status_code=303)
        return rev.kill_switch_state()

    @router.delete("/kill-switch")
    def disengage() -> dict:
        rev.disengage_kill_switch()
        audit.record(event_type=KILL_SWITCH_DISENGAGED, reason="disengaged by operator")
        return rev.kill_switch_state()

    @router.post("/kill-switch/disengage", response_model=None)
    def disengage_form(request: Request) -> HTMLResponse | dict:
        rev.disengage_kill_switch()
        audit.record(event_type=KILL_SWITCH_DISENGAGED, reason="disengaged by operator")
        if _wants_html(request):
            return RedirectResponse(url="/dashboard", status_code=303)
        return rev.kill_switch_state()

    @router.get("/kill-switch")
    def status() -> dict:
        return rev.kill_switch_state()

    return router


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    # any browser request will accept text/html
    return "text/html" in accept
