from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.models import Capture, CoachSession
from app.schemas import CoachEventIn
from app.serialize import capture_dict, session_dict
from app.services.coach import URGENT_MESSAGE, append_event, commit_capture, discard_capture, mint_realtime_session

router = APIRouter(prefix="/coach", tags=["coach"])


def _session(db: Session, session_id: int) -> CoachSession:
    item = db.scalar(
        select(CoachSession).options(selectinload(CoachSession.captures)).where(CoachSession.id == session_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Coach session not found.")
    return item


def _capture(db: Session, capture_id: int) -> Capture:
    item = db.get(Capture, capture_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Capture not found.")
    return item


@router.post("/session")
def create_session(db: Session = Depends(get_db)):
    return mint_realtime_session(db)


@router.get("/sessions/{session_id}")
def read_session(session_id: int, db: Session = Depends(get_db)):
    return session_dict(_session(db, session_id))


@router.post("/sessions/{session_id}/events")
def post_event(session_id: int, body: CoachEventIn, db: Session = Depends(get_db)):
    session = _session(db, session_id)
    result = append_event(db, session, body)
    capture = result["capture"]
    return {
        "session": session_dict(_session(db, session_id)),
        "capture": capture_dict(capture) if capture is not None else None,
        "urgent": result["urgent"],
        "urgent_message": result["urgent_message"] or (URGENT_MESSAGE if result["urgent"] else None),
    }


@router.post("/captures/{capture_id}/commit")
def commit(capture_id: int, db: Session = Depends(get_db)):
    capture = commit_capture(db, _capture(db, capture_id))
    return capture_dict(capture)


@router.post("/captures/{capture_id}/discard")
def discard(capture_id: int, db: Session = Depends(get_db)):
    capture = discard_capture(db, _capture(db, capture_id))
    return capture_dict(capture)
