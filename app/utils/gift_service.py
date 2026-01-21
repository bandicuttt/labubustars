import asyncio

import aiohttp
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest

import config
from app.database import db
from app.database.repositories import UserRepository
from app.database.repositories.gift_issue_repo import GiftIssueRepository
from app.keyboards import inline
from app.templates.texts import after_dart_sub
from app.utils.utils import get_admins

GIFTLY_BASE_URL = "https://stars-rocket.com/api/v1/"
BUY_GIFT_ENDPOINT = "giftly/buyGift"


def _user_mention_or_link(user_id: int, username: str | None) -> str:
    """
    Для админа: если есть username -> @username
    иначе -> ссылка tg://user?id=...
    """
    if username:
        if not username.startswith("@"):
            return f"@{username}"
        return username
    return f"<a href=tg://user?id={user_id}>{user_id}</a>"


def _looks_like_closed_dm_error(message: str) -> bool:
    """
    По доке и реальным кейсам: если пользователь не писал / платные сообщения / закрыта личка.
    В доке прямо перечислены фразы.
    """
    m = (message or "").lower()
    triggers = [
        "платные сообщения",
        "должен написать первым",
        "пользователь не написал",
        "пользователь не писал",
        "написал, чтобы получить подарок",
        "у пользователя включены платные сообщения",
    ]
    return any(t.lower() in m for t in triggers)


async def _get_user_ban_status(user_id: int) -> bool:
    try:
        async with db.get_session() as session:
            user_repo = UserRepository(session)
            db_user = await user_repo.get_user(user_id)
            return bool(db_user.banned) if db_user else False
    except Exception:
        return False


async def issue_gift_via_giftly(
    bot: Bot,
    *,
    user_id: int,
    username: str | None,
    text: str | None = None,
    timeout_sec: int = 20,
) -> bool:
    """
    Отправляет подарок через Giftly Service (stars-rocket.com) по документации пользователя.

    Требования к конфигу (пример атрибутов):
      config.giftly.token: str
      config.giftly.gift_id: str
      config.giftly.base_url: str | None (если хочешь переопределять)
      config.admin.chat_id: int

    Поведение:
    - success -> пишет пользователю "Подарок скоро будет отправлен..." и админу отчёт.
    - ошибка из-за ЛС/платных сообщений -> пишет пользователю инструкцию открыть личку/написать первым.
    - прочие ошибки -> админу детали, пользователю нейтрально.

    Возвращает:
      True если запрос успешно добавлен в очередь (success=true)
      False иначе
    """
    # === получаем настройки из конфига ===

    base_url: str = getattr(getattr(config, "giftly", object()), "base_url", None) or GIFTLY_BASE_URL
    token: str = config.GIFTLY_API_TOKEN
    gift_id: str = config.DARTS_GIFT_ID

    url = base_url.rstrip("/") + "/" + BUY_GIFT_ENDPOINT

    payload: dict[str, str] = {
        "recipient": str(user_id),   # по твоей доке: user_id без @
        "gift_id": str(gift_id),
        "token": str(token),
    }
    if text:
        payload["text"] = text

    session = aiohttp.ClientSession()
    close_session = True

    try:
        async with session.post(url, json=payload, timeout=timeout_sec) as resp:
            # Пытаемся разобрать json, даже если код != 200
            data = None
            try:
                print(f"Giftly response: {resp.status} {await resp.text()}")
                data = await resp.json(content_type=None)
                print(f"Giftly response json: {data}")
            except Exception:
                data = None

            # Успех по доке: {"success": true, "message": "...", "id": 1404}
            if isinstance(data, dict) and data.get("success") is True:
                queue_id = data.get("id")
                gift_count = None
                is_banned = False
                try:
                    async with db.get_session() as session:
                        gift_repo = GiftIssueRepository(session)
                        gift_count = await gift_repo.increment_user_gifts(user_id)
                        user_repo = UserRepository(session)
                        db_user = await user_repo.get_user(user_id)
                        is_banned = bool(db_user.banned) if db_user else False
                except Exception:
                    gift_count = None
                    is_banned = False
                # Пользователю
                try:
                    await bot.send_message(
                        user_id,
                        after_dart_sub,
                    )
                except (TelegramForbiddenError, TelegramBadRequest):
                    # Если юзер заблокировал бота/нельзя писать — всё равно считаем,
                    # что подарок в очереди; просто уведомим админа.
                    pass

                # Админу
                who = _user_mention_or_link(user_id, username)
                gift_count_line = f"\nПолучено подарков: {gift_count}" if gift_count is not None else ""
                for adm in get_admins():
                    try:
                        await bot.send_message(
                            adm,
                            f"✅ Подарок поставлен в очередь.\n"
                            f"Пользователь: {who}\n"
                            f"user_id: {user_id}\n"
                            f"gift_id: {gift_id}\n"
                            f"queue_id: {queue_id}"
                            f"{gift_count_line}",
                            reply_markup=inline.gift_ban_kb(user_id, is_banned),
                        )
                    except Exception as e:
                        print(f"Failed to send message to admin {adm}: {e}")
                return True

            # Ошибки по доке:
            # 401: "Token is required"
            # 400: разные message (неверный токен, недостаточно денег, username не занят, платные сообщения, должен написать первым, ...)
            # Будем ориентироваться на поле message, если есть
            err_msg = ""
            if isinstance(data, dict):
                err_msg = str(data.get("message") or "")
            else:
                err_msg = f"HTTP {resp.status}"

            # Если проблема с ЛС/платными сообщениями
            if resp.status == 400 and _looks_like_closed_dm_error(err_msg):
                try:
                    await bot.send_message(
                        user_id,
                        "⚠️ Я не могу отправить вам подарок, потому что у вас закрыты личные сообщения "
                        "или включены платные сообщения.\n\n"
                        "Пожалуйста: откройте личку (разрешите писать вам),\n"
                    )
                except (TelegramForbiddenError, TelegramBadRequest):
                    pass

                who = _user_mention_or_link(user_id, username)
                is_banned = await _get_user_ban_status(user_id)
                for adm in get_admins():
                    await bot.send_message(
                        adm,
                        f"⚠️ Не удалось поставить подарок в очередь из-за ЛС/платных сообщений.\n"
                        f"Пользователь: {who}\n"
                        f"user_id: {user_id}\n"
                        f"Ответ API: {err_msg}",
                        reply_markup=inline.gift_ban_kb(user_id, is_banned),
                    )
                return False

            # Остальные ошибки — админу детали, пользователю нейтрально
            who = _user_mention_or_link(user_id, username)
            is_banned = await _get_user_ban_status(user_id)
            for adm in get_admins():
                await bot.send_message(
                    adm,
                    f"❌ Ошибка при постановке подарка в очередь.\n"
                    f"Пользователь: {who}\n"
                    f"user_id: {user_id}\n"
                    f"gift_id: {gift_id}\n"
                    f"HTTP: {resp.status}\n"
                    f"Ответ API: {err_msg}",
                    reply_markup=inline.gift_ban_kb(user_id, is_banned),
                )
            try:
                await bot.send_message(
                    user_id,
                    "❌ Не удалось оформить подарок автоматически. Администратор уже уведомлён.",
                )
            except (TelegramForbiddenError, TelegramBadRequest):
                pass

            return False

    except asyncio.TimeoutError:
        who = _user_mention_or_link(user_id, username)
        is_banned = await _get_user_ban_status(user_id)
        for adm in get_admins():
            await bot.send_message(
                adm,
                f"⏳ Таймаут при обращении к Giftly API.\n"
                f"Пользователь: {who}\nuser_id: {user_id}\ngift_id: {gift_id}",
                reply_markup=inline.gift_ban_kb(user_id, is_banned),
            )
        try:
            await bot.send_message(
                user_id,
                "⏳ Сервис подарков временно не отвечает. Попробуйте позже.",
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
        return False

    except Exception as e:
        main_exc = e
        print(f"Ошибка при обращении к Giftly API: {e}")
        who = _user_mention_or_link(user_id, username)
        is_banned = await _get_user_ban_status(user_id)
        for adm in get_admins():
            try:
                await bot.send_message(
                    adm,
                    f"💥 Исключение при выдаче подарка.\n"
                    f"Пользователь: {who}\nuser_id: {user_id}\ngift_id: {gift_id}\n"
                    f"Ошибка: {main_exc}",
                    reply_markup=inline.gift_ban_kb(user_id, is_banned),
                )
            except Exception as send_exc:
                print(f"Ошибка при отправке сообщения админу: {send_exc}")
        try:
            await bot.send_message(
                user_id,
                "❌ Произошла ошибка при выдаче подарка. Администратор уведомлён.",
            )
        except (TelegramForbiddenError, TelegramBadRequest):
            pass
    finally:
        if close_session:
            await session.close()
