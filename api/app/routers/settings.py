from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import SettingsRow
from app.schemas import SettingsPatch
from app.serialize import settings_dict
from app.services.weeks import week_start

router = APIRouter(prefix="/settings", tags=["settings"])


def ensure_settings(db: Session) -> SettingsRow:
    row = db.get(SettingsRow, 1)
    if row is None:
        row = SettingsRow(id=1, timezone="UTC", display_name="")
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("")
def read_settings(db: Session = Depends(get_db)):
    return settings_dict(ensure_settings(db))


@router.patch("")
def update_settings(body: SettingsPatch, db: Session = Depends(get_db)):
    row = ensure_settings(db)
    if body.timezone is not None:
        try:
            week_start(body.timezone)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        row.timezone = body.timezone
    if body.display_name is not None:
        row.display_name = body.display_name
    db.commit()
    db.refresh(row)
    return settings_dict(row)
