"""Relay Postgres `todo_updates` NOTIFY payloads to authenticated WebSockets (PR 06 + PR 10)."""

from __future__ import annotations

import asyncio
import logging
from urllib.parse import quote_plus

import asyncpg
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from todos.pg_notify_security import todo_update_payload_allowed_for_user


logger = logging.getLogger(__name__)


def _postgres_dsn() -> str:
    """Build asyncpg DSN from Django DB settings (uses test DB name under pytest-django)."""
    db = settings.DATABASES['default']
    user = quote_plus(str(db.get('USER', '') or ''))
    password = quote_plus(str(db.get('PASSWORD', '') or ''))
    host = str(db.get('HOST', '') or 'localhost')
    port = str(db.get('PORT', '') or '5432')
    return f'postgresql://{user}:{password}@{host}:{port}/{db["NAME"]}'


class TodoConsumer(AsyncWebsocketConsumer):
    _listen_task: asyncio.Task | None = None
    _stop_listen: asyncio.Event | None = None

    async def connect(self) -> None:
        user = self.scope['user']
        if not user.is_authenticated:
            await self.close()
            return
        await self.accept()
        self._stop_listen = asyncio.Event()
        self._listen_task = asyncio.create_task(self._listen_loop(user.pk))

    async def disconnect(self, code: int) -> None:  # noqa: ARG002 — Channels API contract
        if self._stop_listen is not None:
            self._stop_listen.set()
        task = self._listen_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _listen_loop(self, user_pk: int) -> None:
        conn: asyncpg.Connection | None = None

        async def on_notify(
            _: asyncpg.Connection,
            __: int,
            ___: str,
            payload: str | None,
        ) -> None:
            if payload is None or not todo_update_payload_allowed_for_user(
                payload,
                viewer_pk=user_pk,
            ):
                return
            try:
                await self.send(text_data=payload)
            except Exception:
                logger.exception('Failed to relay todo_updates payload')

        try:
            conn = await asyncpg.connect(dsn=_postgres_dsn())
            await conn.add_listener('todo_updates', on_notify)
            await self._stop_listen.wait()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('LISTEN todo_updates failed')
        finally:
            if conn is not None:
                try:
                    await conn.remove_listener('todo_updates', on_notify)
                except Exception:
                    logger.debug('remove_listener failed during shutdown', exc_info=True)
                await conn.close()
