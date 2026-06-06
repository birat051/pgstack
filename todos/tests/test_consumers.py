import asyncio
import json

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import TransactionTestCase, override_settings

from todos.consumers import TodoConsumer
from todos.models import Todo, TodoStatus


@override_settings(ALLOWED_HOSTS=['testserver', 'localhost', '127.0.0.1'])
class TodoConsumerTests(TransactionTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.owner = get_user_model().objects.create_user(
            username='ws_owner',
            password='testpass123!',
            email='ws@example.com',
        )

    def _communicator(self, user) -> WebsocketCommunicator:
        communicator = WebsocketCommunicator(TodoConsumer.as_asgi(), '/ws/todos/')
        communicator.scope['user'] = user
        return communicator

    def test_rejects_anonymous_connection(self) -> None:
        communicator = self._communicator(AnonymousUser())
        connected, _ = async_to_sync(communicator.connect)()
        self.assertFalse(connected)

    def test_accepts_authenticated_connection(self) -> None:
        async def exercise() -> None:
            communicator = self._communicator(self.owner)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await asyncio.sleep(0.2)
            await communicator.disconnect()

        async_to_sync(exercise)()

    def test_forwards_owned_todo_notify_payload(self) -> None:
        owner = self.owner

        @database_sync_to_async
        def create_owned_todo() -> None:
            Todo.objects.create(
                title='Live row',
                notes='',
                status=TodoStatus.PENDING,
                owner=owner,
            )

        async def exercise() -> str:
            communicator = self._communicator(owner)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await asyncio.sleep(0.2)
            await create_owned_todo()
            return await communicator.receive_from(timeout=5)

        raw = async_to_sync(exercise)()
        payload = json.loads(raw)
        self.assertEqual(payload['title'], 'Live row')
        self.assertEqual(payload['owner_id'], owner.pk)

    def test_does_not_forward_other_users_todo_notify(self) -> None:
        owner = self.owner
        other = get_user_model().objects.create_user(
            username='ws_other',
            password='testpass123!',
            email='other@example.com',
        )

        @database_sync_to_async
        def create_foreign_todo() -> None:
            Todo.objects.create(
                title='Foreign row',
                notes='',
                status=TodoStatus.PENDING,
                owner=other,
            )

        async def exercise() -> None:
            communicator = self._communicator(owner)
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await asyncio.sleep(0.2)
            await create_foreign_todo()
            with self.assertRaises((asyncio.TimeoutError, asyncio.CancelledError)):
                await communicator.receive_from(timeout=1)
            # Timeout cancels the application task; avoid a second disconnect.
            communicator.stop(exceptions=False)

        async_to_sync(exercise)()
