import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.research_lab import ResearchNoteCreate, ResearchNoteResponse
from app.core.auth import AuthenticatedUser
from app.models import ResearchNote

logger = logging.getLogger(__name__)


async def create_research_note(
    session: AsyncSession,
    user: AuthenticatedUser,
    payload: ResearchNoteCreate,
) -> ResearchNoteResponse:
    note = ResearchNote(
        owner_user_id=user.id,
        title=payload.title.strip(),
        body=payload.body,
        tags=[tag.strip() for tag in payload.tags if tag.strip()],
        experiment_id=payload.experiment_id,
    )
    session.add(note)
    await session.commit()
    await session.refresh(note)
    logger.info(
        "research_note_created",
        extra={"note_id": str(note.id), "owner_user_id": user.id},
    )
    return _note_response(note)


async def list_research_notes(
    session: AsyncSession,
    user: AuthenticatedUser,
    *,
    limit: int = 100,
) -> list[ResearchNoteResponse]:
    notes = await session.scalars(
        select(ResearchNote)
        .where(ResearchNote.owner_user_id == user.id)
        .order_by(ResearchNote.created_at.desc())
        .limit(limit)
    )
    return [_note_response(note) for note in notes]


async def delete_research_note(
    session: AsyncSession,
    user: AuthenticatedUser,
    note_id: uuid.UUID,
) -> bool:
    note = await session.scalar(
        select(ResearchNote)
        .where(ResearchNote.id == note_id)
        .where(ResearchNote.owner_user_id == user.id)
    )
    if note is None:
        return False
    await session.delete(note)
    await session.commit()
    logger.info(
        "research_note_deleted",
        extra={"note_id": str(note_id), "owner_user_id": user.id},
    )
    return True


def _note_response(note: ResearchNote) -> ResearchNoteResponse:
    return ResearchNoteResponse(
        id=note.id,
        title=note.title,
        body=note.body,
        tags=list(note.tags or []),
        experiment_id=note.experiment_id,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )
