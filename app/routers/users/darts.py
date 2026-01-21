from contextlib import suppress

from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from app.database import db, redis_pool
from app.database.repositories import UserRepository
from app.filters import IsPrivate
from app.keyboards import inline
from app.templates import texts
from app.routers.start import send_main_menu
from app.utils.gift_service import issue_gift_via_giftly
from op.services.op_service import op_client


darts_router = Router(name="darts_router")

DARTS_SPONSORS_PER_ATTEMPT = 4
DARTS_ALLOW_MANUAL_MULTIUSE = True
DARTS_MANUAL_USED_TTL = 60*60*5

DARTS_STAGE_ORDER = ("manual", "flyer", "subgram", "tgrass", "botohub")
DARTS_STAGE_KEY = "darts:stage:{user_id}"
DARTS_REF_BONUS_KEY = "darts:ref_bonus:{user_id}"
DARTS_STAGE_STATE_KEY = "darts_stage"
DARTS_FLOW_STATE_KEY = "darts_flow"
DARTS_MANUAL_USED_KEY = "darts:manual_used:{user_id}"
DARTS_PENDING_KEY = "darts:pending:{user_id}"
DARTS_PENDING_META_KEY = "darts:pending_meta:{user_id}"
DARTS_REF_CHECK_CB = "darts:check_referrals"
DARTS_DONE_CB = "check_dart"


async def issue_dart_gift(bot: Bot, user_id: int, username: str | None) -> None:
    await issue_gift_via_giftly(
        bot,
        user_id=user_id,
        username=username,
    )


def is_bullseye(value: int | None) -> bool:
    return value == 6


async def get_stage_index(user_id: int) -> int:
    async with redis_pool.get_connection() as redis:
        value = await redis.get(DARTS_STAGE_KEY.format(user_id=user_id))
    if value is None:
        return 0
    return int(value)


async def set_stage_index(user_id: int, index: int) -> None:
    async with redis_pool.get_connection() as redis:
        await redis.set(DARTS_STAGE_KEY.format(user_id=user_id), index)


async def get_pending_attempt(user_id: int) -> tuple[bool, int | None, str | None]:
    async with redis_pool.get_connection() as redis:
        pending = bool(await redis.get(DARTS_PENDING_KEY.format(user_id=user_id)))
        if not pending:
            return False, None, None
        stage_index_raw = await redis.hget(DARTS_PENDING_META_KEY.format(user_id=user_id), "stage_index")
        flow_state_raw = await redis.hget(DARTS_PENDING_META_KEY.format(user_id=user_id), "flow_state")
    stage_index = int(stage_index_raw) if stage_index_raw is not None else None
    flow_state = flow_state_raw.decode() if isinstance(flow_state_raw, (bytes, bytearray)) else flow_state_raw
    return True, stage_index, flow_state


async def set_pending_attempt(
    user_id: int,
    stage_index: int | None = None,
    flow_state: str | None = None,
) -> None:
    async with redis_pool.get_connection() as redis:
        await redis.set(DARTS_PENDING_KEY.format(user_id=user_id), 1)
        if stage_index is not None:
            await redis.hset(DARTS_PENDING_META_KEY.format(user_id=user_id), "stage_index", stage_index)
        if flow_state is not None:
            await redis.hset(DARTS_PENDING_META_KEY.format(user_id=user_id), "flow_state", flow_state)


async def clear_pending_attempt(user_id: int) -> None:
    async with redis_pool.get_connection() as redis:
        await redis.delete(DARTS_PENDING_KEY.format(user_id=user_id))
        await redis.delete(DARTS_PENDING_META_KEY.format(user_id=user_id))


async def has_manual_sponsors_used(user_id: int) -> bool:
    async with redis_pool.get_connection() as redis:
        return bool(await redis.get(DARTS_MANUAL_USED_KEY.format(user_id=user_id)))


async def set_manual_sponsors_used(user_id: int) -> None:
    async with redis_pool.get_connection() as redis:
        await redis.set(
            DARTS_MANUAL_USED_KEY.format(user_id=user_id),
            1,
            ex=DARTS_MANUAL_USED_TTL,
        )


async def clear_manual_sponsors_used(user_id: int) -> None:
    async with redis_pool.get_connection() as redis:
        await redis.delete(DARTS_MANUAL_USED_KEY.format(user_id=user_id))


async def get_stage_sponsors(
    stage: str,
    user_id: int,
    language_code: str,
    message: types.Message | types.CallbackQuery,
) -> types.InlineKeyboardMarkup | None:
    if stage == "manual":
        if not DARTS_ALLOW_MANUAL_MULTIUSE and await has_manual_sponsors_used(user_id):
            return None
        return await op_client.check(
            user_id=user_id,
            language_code=language_code,
            message=message,
            no_flyer=True,
            no_subgram=True,
            no_manual=False,
            done_cb=DARTS_DONE_CB,
        )
    if stage == "flyer":
        return await op_client.check(
            user_id=user_id,
            language_code=language_code,
            message=message,
            no_flyer=False,
            no_subgram=True,
            no_manual=True,
            done_cb=DARTS_DONE_CB,
            max_op=DARTS_SPONSORS_PER_ATTEMPT,
        )
    if stage == "subgram":
        return await op_client.check(
            user_id=user_id,
            language_code=language_code,
            message=message,
            no_flyer=True,
            no_subgram=False,
            no_manual=True,
            done_cb=DARTS_DONE_CB,
            max_op=DARTS_SPONSORS_PER_ATTEMPT,
        )
    if stage == "tgrass":
        return await op_client.check_tgrass(
            user_id=user_id,
            language_code=language_code,
            message=message,
            done_cb=DARTS_DONE_CB,
            max_op=DARTS_SPONSORS_PER_ATTEMPT,
        )
    if stage == "botohub":
        return await op_client.check_botohub(
            user_id=user_id,
            done_cb=DARTS_DONE_CB,
        )
    return None


async def find_sponsors(
        user_id: int,
        language_code: str,
        message: types.Message | types.CallbackQuery,
        start_index: int | None = None,
) -> tuple[int | None, types.InlineKeyboardMarkup | None]:
    start_index = start_index if start_index is not None else await get_stage_index(user_id)
    for offset in range(len(DARTS_STAGE_ORDER)):
        stage_index = (start_index + offset) % len(DARTS_STAGE_ORDER)
        stage = DARTS_STAGE_ORDER[stage_index]
        reply_markup = await get_stage_sponsors(stage, user_id, language_code, message)
        if reply_markup:
            return stage_index, reply_markup
    return None, None


async def send_no_sponsors(message: types.Message) -> None:
    bot = await message.bot.get_me()
    ref_link = f"https://t.me/{bot.username}?start={message.from_user.id}"
    await message.answer(
        texts.darts_no_sponsors_message,
        reply_markup=inline.friends_invite_kb(ref_link),
    )


@darts_router.callback_query(F.data == "start_dart", IsPrivate(), StateFilter("*"))
async def start_dart(call: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await call.message.delete()

    pending, pending_stage_index, pending_flow_state = await get_pending_attempt(call.from_user.id)
    if pending:
        stage_index = pending_stage_index if pending_stage_index is not None else await get_stage_index(call.from_user.id)
        flow_state = pending_flow_state or "retry"
        reply_markup = await get_stage_sponsors(
            stage=DARTS_STAGE_ORDER[stage_index],
            user_id=call.from_user.id,
            language_code=(call.from_user.language_code or "ru"),
            message=call,
        )
        if reply_markup:
            await state.update_data(
                {
                    DARTS_STAGE_STATE_KEY: stage_index,
                    DARTS_FLOW_STATE_KEY: flow_state,
                }
            )
            message_text = (
                texts.darts_retry_subscribe_message
                if flow_state == "retry"
                else texts.dart_hit_message
            )
            return await call.message.answer(message_text, reply_markup=reply_markup)
        return await send_main_menu(call.message)

    await set_pending_attempt(call.from_user.id)

    dart_message = await call.message.answer_dice("🎯")
    dart_value = dart_message.dice.value if dart_message.dice else None
    if not is_bullseye(dart_value):
        stage_index, reply_markup = await find_sponsors(
            user_id=call.from_user.id,
            language_code=(call.from_user.language_code or "ru"),
            message=dart_message,
        )
        if reply_markup:
            await set_pending_attempt(
                call.from_user.id,
                stage_index=stage_index,
                flow_state="retry",
            )
            await state.update_data(
                {
                    DARTS_STAGE_STATE_KEY: stage_index,
                    DARTS_FLOW_STATE_KEY: "retry",
                }
            )
            return await call.message.answer(
                texts.darts_retry_subscribe_message,
                reply_markup=reply_markup,
            )
        return await send_no_sponsors(call.message)

    stage_index, reply_markup = await find_sponsors(
        user_id=call.from_user.id,
        language_code=(call.from_user.language_code or "ru"),
        message=dart_message,
    )
    if reply_markup:
        await set_pending_attempt(
            call.from_user.id,
            stage_index=stage_index,
            flow_state="gift",
        )
        await state.update_data(
            {
                DARTS_STAGE_STATE_KEY: stage_index,
                DARTS_FLOW_STATE_KEY: "gift",
            }
        )
        return await call.message.answer(texts.dart_hit_message, reply_markup=reply_markup)

    return await send_no_sponsors(call.message)


@darts_router.callback_query(F.data == DARTS_DONE_CB, IsPrivate(), StateFilter("*"))
async def check_dart(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    stage_index = data.get(DARTS_STAGE_STATE_KEY)
    flow_state = data.get(DARTS_FLOW_STATE_KEY)
    if stage_index is None:
        pending, pending_stage_index, pending_flow_state = await get_pending_attempt(call.from_user.id)
        if not pending or pending_stage_index is None:
            await call.answer()
            return await send_main_menu(call.message)
        stage_index = pending_stage_index
        flow_state = pending_flow_state or flow_state

    stage = DARTS_STAGE_ORDER[stage_index]
    reply_markup = await get_stage_sponsors(
        stage=stage,
        user_id=call.from_user.id,
        language_code=(call.from_user.language_code or "ru"),
        message=call,
    )

    if reply_markup:
        with suppress(TelegramBadRequest, TelegramForbiddenError):
            await call.message.delete()
        await call.answer()
        return await call.message.answer(text=texts.darts_retry_subscribe_message, reply_markup=reply_markup)

    with suppress(TelegramBadRequest, TelegramForbiddenError):
        await call.message.delete()

    await clear_pending_attempt(call.from_user.id)
    await state.clear()

    if stage == "manual" and not DARTS_ALLOW_MANUAL_MULTIUSE:
        await set_manual_sponsors_used(call.from_user.id)
    if stage == "tgrass":
        await op_client.tgrass_reset_offers(call.from_user.id)

    async with db.get_session() as session:
        user_repo = UserRepository(session)
        db_user = await user_repo.get_user(call.from_user.id)
        updates: dict[str, object] = {"darts_op_count": (db_user.darts_op_count or 0) + 1}
        if flow_state != "retry":
            updates["dart_gift_received"] = True
        await user_repo.update_user(call.from_user.id, **updates)

    if flow_state == "retry":
        await set_stage_index(call.from_user.id, (stage_index + 1) % len(DARTS_STAGE_ORDER))
        await call.message.answer(
            texts.darts_retry_ready_message,
            reply_markup=inline.darts_after_win_kb(),
        )
        return None

    await set_stage_index(call.from_user.id, (stage_index + 1) % len(DARTS_STAGE_ORDER))
    if not DARTS_ALLOW_MANUAL_MULTIUSE:
        await clear_manual_sponsors_used(call.from_user.id)
    await issue_dart_gift(call.bot, call.from_user.id, call.from_user.username)

    await call.message.answer(
        text=texts.after_dart_sub,
        reply_markup=inline.darts_after_win_kb(),
    )


@darts_router.callback_query(F.data == DARTS_REF_CHECK_CB, IsPrivate(), StateFilter("*"))
async def check_referrals_for_darts(call: types.CallbackQuery):
    async with db.get_session() as session:
        user_repo = UserRepository(session)
        total_subbed = await user_repo.get_users(
            ref=str(call.from_user.id),
            subbed=True,
            count=True,
        )

    async with redis_pool.get_connection() as redis:
        used_raw = await redis.get(DARTS_REF_BONUS_KEY.format(user_id=call.from_user.id))
        used = int(used_raw) if used_raw is not None else 0

    available = total_subbed // 3
    if available <= used:
        await call.answer()
        return await call.message.answer(
            texts.darts_referral_progress_message.format(current=total_subbed),
            reply_markup=inline.friends_invite_kb(
                f"https://t.me/{(await call.bot.get_me()).username}?start={call.from_user.id}"
            ),
        )

    async with redis_pool.get_connection() as redis:
        await redis.incr(DARTS_REF_BONUS_KEY.format(user_id=call.from_user.id))

    await call.answer()
    await call.message.answer(
        texts.darts_referral_bonus_message,
        reply_markup=inline.darts_after_win_kb(),
    )
