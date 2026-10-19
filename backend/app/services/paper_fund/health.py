"""Persisted job health; a successful HTTP request is not a worker heartbeat."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.models import WorkerHeartbeat

DEADLINES = {'execution': 90, 'history': 720, 'metadata': 720}


@asynccontextmanager
async def track_job(factory, name):
    started = datetime.now(timezone.utc)
    async with factory() as session:
        await session.execute(insert(WorkerHeartbeat).values(name=name, started_at=started).on_conflict_do_update(
            index_elements=['name'], set_={'started_at': started}))
        await session.commit()
    try:
        yield
    except BaseException as error:
        async with factory() as session:
            row = await session.get(WorkerHeartbeat, name)
            if row.started_at == started:
                row.error_code = type(error).__name__[:64]
                await session.commit()
        raise
    else:
        async with factory() as session:
            row = await session.get(WorkerHeartbeat, name)
            if row.started_at == started:
                row.completed_at, row.error_code = datetime.now(timezone.utc), None
                await session.commit()


def job_status(name, row, now):
    if row is None or row.completed_at is None:
        status = 'unavailable'
    elif row.error_code or (now-row.completed_at).total_seconds() > DEADLINES[name] or row.completed_at > now:
        status = 'delayed'
    else:
        status = 'healthy'
    return {'name': name, 'status': status, 'last_completed_at': row.completed_at if row else None,
            'last_started_at': row.started_at if row else None,
            'error_code': row.error_code if row else None}


async def worker_health(session, now=None):
    now = now or datetime.now(timezone.utc)
    rows = {row.name: row for row in await session.scalars(select(WorkerHeartbeat))}
    return [job_status(name, rows.get(name), now) for name in DEADLINES]
