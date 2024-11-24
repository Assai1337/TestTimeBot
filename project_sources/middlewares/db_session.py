from aiogram.dispatcher.middlewares.base import BaseMiddleware
from aiogram import types
from typing import Any, Dict, Callable, Awaitable
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
import logging

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_maker: async_sessionmaker):
        self.session_maker = session_maker
        super().__init__()

    async def __call__(
            self,
            handler: Callable[[types.Update, Dict[str, Any]], Awaitable[Any]],
            event: types.Update,
            data: Dict[str, Any],
    ) -> Any:
        try:
            async with self.session_maker() as session:
                data["session"] = session
                return await handler(event, data)
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Ошибка в Middleware DbSessionMiddleware: {e}")
            raise
