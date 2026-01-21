from urllib.parse import quote

import config

from app.templates import button_texts
from app.database import models


def tasks_subgram_kb(tasks_list):
    # Создаём список всех кнопок задач
    task_buttons = []
    for sub in tasks_list:
        if sub['link'] is not None:
            if 'bot' in sub['type']:
                button = {'text': button_texts.sub_is_bot_button, 'url': sub['link']}
            elif 'channel' in sub['type']:
                button = {'text': button_texts.sub_is_channel_button, 'url': sub['link']}
            else:
                button = {'text': button_texts.sub_is_give_boost, 'url': sub['link']}
            task_buttons.append(button)
    
    # Группируем кнопки по 2 в ряду
    grouped_buttons = [task_buttons[i:i+2] for i in range(0, len(task_buttons), 2)]
    
    # Добавляем кнопку проверки в отдельный ряд
    keyboard = {
        'inline_keyboard': grouped_buttons + [
            [
                {'text': button_texts.check_button, 'callback_data': 'check_subgram_tasks'}
            ],
            [
                {'text': '⬅️ В главное меню ', 'callback_data': 'main_menu'}
            ]
        ]
    }
    return keyboard

def tasks_flyer_kb(tasks_list):
    # Создаём список всех кнопок задач
    task_buttons = []
    for sub in tasks_list:
        if sub['link'] is not None:
            if 'start bot' in sub['task']:
                button = {'text': button_texts.sub_is_bot_button, 'url': sub['link']}
            elif 'subscribe channel' in sub['task']:
                button = {'text': button_texts.sub_is_channel_button, 'url': sub['link']}
            else:  # для give boost и других задач
                button = {'text': button_texts.sub_is_give_boost, 'url': sub['link']}
            task_buttons.append(button)
    
    # Группируем кнопки по 2 в ряду
    grouped_buttons = [task_buttons[i:i+2] for i in range(0, len(task_buttons), 2)]
    
    # Добавляем кнопку проверки в отдельный ряд
    keyboard = {
        'inline_keyboard': grouped_buttons + [
            [
                {'text': button_texts.check_button, 'callback_data': 'check_flyer_tasks'}
            ],
            [
                {'text': button_texts.skip_button, 'callback_data': 'skip_flyer'}
            ],
            [
                {'text': '⬅️ В главное меню ', 'callback_data': 'main_menu'}
            ]
        ]
    }
    return keyboard

def admin_stats_kb() -> dict:

    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.admin_stats_today_button, 'callback_data': f'admin_stat:today'},
            {'text': button_texts.admin_stats_week_button, 'callback_data': f'admin_stat:week'},
            {'text': button_texts.admin_stats_month_button, 'callback_data': f'admin_stat:month'}
        ],
    ]}

    return keyboard

def cancel_kb() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.cancel_button, 'callback_data': 'close'},
        ]
    ]}

    return keyboard

def admin_mailing_filters_kb(state_data) -> dict:
    keyboard = {'inline_keyboard':[
        [
            {
                'text': ('✔️ ' if state_data['is_premium'] else '') + button_texts.is_premium_mailing_button,
                'callback_data': 'mailing:is_premium'
            },
        ],
        [
            {
                'text': ('✔️ ' if state_data['is_chats'] else '') + button_texts.only_chats_mailing_button,
                'callback_data': 'mailing:is_chats'
            },
        ],
        [
            {
                'text': ('✔️ ' if state_data['is_pin'] else '') + button_texts.is_pin_mailing_button,
                'callback_data': 'mailing:is_pin'
            },
        ],
        [
            {'text': button_texts.continue_button, 'callback_data': 'mailing:continue'},
        ],
        [
            {'text': button_texts.cancel_button, 'callback_data': 'close'},
        ]
    ]}

    return keyboard

def admin_mailing_pre_check_kb() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.continue_button, 'callback_data': 'start_mail'},
        ],
        [
            {'text': button_texts.cancel_button, 'callback_data': 'close'},
        ]
    ]}

    return keyboard

def subgram_unsubscribed_kb(sponsor_url) -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.sub_is_channel_button, 'url': sponsor_url},
        ],
    ]}

    return keyboard


def admin_adverts(adverts: list[models.Advert], raw: int):
    keyboard = {'inline_keyboard': []}

    raw = max(0, min(raw, len(adverts)))
    adverts_data = adverts[raw:raw + 5]

    for i in adverts_data:
        keyboard['inline_keyboard'].append([
            {
                'text': '🟢' if i.status else '❌',
                'callback_data': f'adverts:status:{i.id}:{raw}'
            },
            {
                'text': ('👋 ' if i.only_start else '🌆 ') + i.title,
                'callback_data': f'...'
            },
            {
                'text': f'🎯 {i.viewed} / {i.views}',
                'callback_data': f'...'
            },
            {
                'text': f'👀',
                'callback_data': f'adverts:show:{i.id}:{raw}'
            },
            {
                'text': f'🗑',
                'callback_data': f'adverts:delete:{i.id}:{raw}'
            },
        ])

    keyboard['inline_keyboard'].append([
        {'text': '➕', 'callback_data': f'adverts:create:0:{raw}'}
    ])

    navigation_buttons = []
    if len(adverts) > 5:
        if raw > 0:
            navigation_buttons.append({
                'text': '⬅️', 'callback_data': f'adverts_swipe:{raw - 5}'
            })
        if raw + 5 < len(adverts):
            navigation_buttons.append({
                'text': '➡️', 'callback_data': f'adverts_swipe:{raw + 5}'
            })

    if navigation_buttons:
        keyboard['inline_keyboard'].append(navigation_buttons)

    return keyboard


def admin_subscribes(subscribes: list[models.Subscribe], raw: int):
    keyboard = {'inline_keyboard': []}

    raw = max(0, min(raw, len(subscribes)))
    subscribes_data = subscribes[raw:raw + 5]

    for i in subscribes_data:
        keyboard['inline_keyboard'].append([
            {
                'text': '🟢' if i.status else '❌',
                'callback_data': f'subscribes:status:{i.id}:{raw}'
            },
            {
                'text': ('🗒 ' if i.is_task else '💰 ') + i.title,
                'callback_data': f'...'
            },
            {
                'text': f'🎯 {i.subscribed_count} / {i.subscribe_count}',
                'callback_data': f'...'
            },
            {
                'text': f'🔗',
                'url': i.url
            },
            {
                'text': f'🗑',
                'callback_data': f'subscribes:delete:{i.id}:{raw}'
            },
        ])

    keyboard['inline_keyboard'].append([
        {'text': '➕', 'callback_data': f'subscribes:create:0:{raw}'}
    ])

    navigation_buttons = []
    if len(subscribes) > 5:
        if raw > 0:
            navigation_buttons.append({
                'text': '⬅️', 'callback_data': f'subscribes_swipe:{raw - 5}'
            })
        if raw + 5 < len(subscribes):
            navigation_buttons.append({
                'text': '➡️', 'callback_data': f'subscribes_swipe:{raw + 5}'
            })

    if navigation_buttons:
        keyboard['inline_keyboard'].append(navigation_buttons)

    return keyboard

def admin_subscribe_type_kb() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.subscribe_create_is_check_true_type, 'callback_data': 'subscribes_create:check_true'},
            {'text': button_texts.subscribe_create_is_check_false_type, 'callback_data': 'subscribes_create:check_false'},
        ],
        [
            {'text': button_texts.cancel_button, 'callback_data': 'close'},
        ]
    ]}

    return keyboard

def admin_referrals(referrals: list[str], raw: int):
    keyboard = {'inline_keyboard': []}

    raw = max(0, min(raw, len(referrals)))
    referrals_data = referrals[raw:raw + 5]

    for i in referrals_data:
        keyboard['inline_keyboard'].append([
            {
                'text': f"{i['ref']} 🔗",
                'callback_data': f'referals:get_stat:{i["ref"]}'
            },
        ])

    navigation_buttons = []
    if len(referrals) > 5:
        if raw > 0:
            navigation_buttons.append({
                'text': '⬅️', 'callback_data': f'referrals_swipe:{raw - 5}'
            })
        if raw + 5 < len(referrals):
            navigation_buttons.append({
                'text': '➡️', 'callback_data': f'referrals_swipe:{raw + 5}'
            })

    keyboard['inline_keyboard'].append([{
            'text': '💎 Создать ссылку', 'callback_data': f'referals:create:0'
        }])

    if navigation_buttons:
        keyboard['inline_keyboard'].append(navigation_buttons)

    return keyboard


def subscribes_kb(subscribes: list[models.Subscribe]) -> dict:
    keyboard = {
        'inline_keyboard': [
            [
                {'text': button_texts.sub_is_bot_button, 'url': sub.url} if sub.is_bot
                else {'text': button_texts.sub_is_channel_button, 'url': sub.url},
            ] for sub in subscribes
        ] + [
            [
                {'text': button_texts.check_button, 'callback_data': 'check_subscribe'},
            ],
            [
                {'text': '⬅️ В главное меню ', 'callback_data': 'main_menu'}
            ]
        ]
    }

    return keyboard

def top_users_kb() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.top_users_today_button, 'callback_data': 'top_users:today'},
            {'text': button_texts.top_users_all_button, 'callback_data': 'top_users:all'}
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}

    return keyboard

def get_stars_kb(bot_username, user_id):
    keyboard = {'inline_keyboard':[
        [
            {'text': '🔗 Отправить друзьям', 'url': 'tg://msg_url?url=https://t.me/{}?start={}&text=Дарю тебе ⭐️, переходи в бота и забирай!'.format(bot_username, user_id)}
        ],
        [
            {'text': '+2⭐️ за старых друзей', 'callback_data': 'old_friends'}
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}

    return keyboard


def profile_user() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': '🎫 Промокод', 'callback_data': 'promocode'},
            {'text': '🎁 Ежедневка', 'callback_data': 'daily_bonus'}
        ],
        [
            {'text': '+2⭐️ за старых друзей', 'callback_data': 'old_friends'},
        ],
        [
            {'text': '💫 Перевести ⭐️ другу', 'callback_data': 'transfer_stars'}
        ],
        [
            {'text': '⬅️ В главное меню ', 'callback_data': 'main_menu'}
        ]
    ]}

    return keyboard

def withdrawal_menu_kb():
    keyboard = {'inline_keyboard':[
        [
            {'text': f'👤 Изменить получателя', 'callback_data': 'withdrawal_change_user'}
        ],
        [
            {'text': '🎁 Вывести подарком (от 15⭐️)', 'callback_data': 'withdrawal_gifts'}
        ],
        [
            {'text': '🎉 TG Premium 6 мес. (1700⭐️)', 'callback_data': 'withdrawal_premium'},
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}

    return keyboard

def main_user() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': '✨ Кликер', 'callback_data': 'clicker'}
        ],
        [
            {'text': '⭐️ Заработать звёзды', 'callback_data': 'get_stars'}
        ],
        [
            {'text': '👤 Профиль', 'callback_data': 'profile'},
            {'text': '💰 Вывод звезд', 'callback_data': 'withdrawal'}
        ],
        [
            {'text': '📝 Задания', 'callback_data': 'tasks'},
            {'text': '📚 Инструкция', 'callback_data': 'instruction'}
        ],
        [
            {'text': '🏆 Топ', 'callback_data': 'top_users:today'},
            {'text': '🎰 Рулетка', 'callback_data': 'roulette'}
        ],
        [
            {'text': '💌 Выплаты', 'url': config.REVIEWS_CHANNEL_URL}
        ]
    ]}

    return keyboard

def approve_kb() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': '✅ Подтвердить', 'callback_data': '1'},
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
        
    ]}

    return keyboard


def tasks_kb(subscribes: list[models.Subscribe]) -> dict:
    keyboard = {
        'inline_keyboard': [
            [
                # Берем по 2 подписки за раз
                {'text': button_texts.sub_is_bot_button, 'url': sub.url} if sub.is_bot
                else {'text': button_texts.sub_is_channel_button, 'url': sub.url}
                for sub in subscribes[i:i + 2]  # Срез, который берет 2 элемента
            ] for i in range(0, len(subscribes), 2)  # Итерируемся с шагом 2
        ] + [
            [
                {'text': button_texts.check_button, 'callback_data': 'check_tasks'},
            ],
            [
                {'text': '⬅️ В главное меню ', 'callback_data': 'main_menu'}
            ]
        ]
    }

    return keyboard


def games_main_menu() -> dict:
    keyboard = {'inline_keyboard':[
        # [
        #     {'text': button_texts.darts_game, 'callback_data': 'game:darts:games_menu'},
        # ],
        # [
        #     {'text': button_texts.football_game, 'callback_data': 'game:football:games_menu'},
        # ],
        # [
        #     {'text': button_texts.bowling_game, 'callback_data': 'game:bowling:games_menu'},
        # ],
        [
            {'text': button_texts.slots_game, 'callback_data': 'game:slots:games_menu'},
        ],
        # [
        #     {'text': button_texts.basketball_game, 'callback_data': 'game:basketball:games_menu'},
        # ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}

    return keyboard

def insturction_kb() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}
    
    return keyboard

def selected_game_menu(game: str) -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.start_game, 'callback_data': f'game:{game}:bet_menu'},
        ],
        [
            {'text': button_texts.back_button, 'callback_data': 'games_main_menu'},
            {'text': button_texts.game_rules_button, 'callback_data': f'game:{game}:rules'},
        ],
    ]}

    if game == 'lottery':
        keyboard['inline_keyboard'][0] = [
            {
                'text': button_texts.lottery_buy_ticket, 'callback_data': 'lottery:buy_ticket'
            }
        ]
    
    return keyboard


def darts_after_win_kb() -> dict:
    keyboard = {'inline_keyboard': [
        [
            {'text': "🎯 Кинуть дротик ещё раз", 'callback_data': 'start_dart'},
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}
    return keyboard


def friends_invite_kb(ref_link: str) -> dict:
    share_url = f"https://t.me/share/url?url={quote(ref_link)}"
    keyboard = {'inline_keyboard': [
        [
            {'text': '📨 Пригласить 3 друзей', 'url': share_url},
        ],
        [
            {'text': '✅ Проверить друзей', 'callback_data': 'darts:check_referrals'},
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}
    return keyboard


def pseudo_gift_kb(mini_game_btn: bool | str = True, start_bonus_url: str | None = None, bonus_txt: str = None) -> dict:
    mini_game_btn_txt = mini_game_btn if isinstance(mini_game_btn, str) else "🎣 Словить рыбку"
    keyboard = {'inline_keyboard': [
        [
            {'text': mini_game_btn_txt, 'callback_data': 'fish:start'},
        ],
    ]}

    keyboard = keyboard if mini_game_btn else {'inline_keyboard': []}
    bonus_url = start_bonus_url or getattr(config, "START_BONUS_URL", None)
    if bonus_url:
        bonus_txt = bonus_txt or "Забрать 100⭐ за старт ↗"
        keyboard['inline_keyboard'].append([
            {'text': bonus_txt, 'url': bonus_url},
        ])

    return keyboard


def subscribe_our_channels() -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.sub_is_channel_button, 'url': config.MAIN_CHANNEL_URL},
        ],
        [
            {'text': button_texts.check_button, 'callback_data': 'check_subscribe'},
        ],
    ]}

    return keyboard

def back_kb(calldata: str, text: str = button_texts.back_button) -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': text, 'callback_data': calldata},
        ],
    ]}

    return keyboard


def game_bet_menu(game: str, bet: float) -> dict:
    keyboard = {'inline_keyboard':[
        [
            {'text': '➖', 'callback_data': f'pre_start:{game}:lower_bet'},
            {'text': f'{round(float(bet), 2)} 💰', 'callback_data': f'...'},
            {'text': '➕', 'callback_data': f'pre_start:{game}:highter_bet'},
        ],
        [
            {'text': button_texts.min_bet_button, 'callback_data': f'pre_start:{game}:min_bet'},
            {'text': button_texts.delete_bet_button, 'callback_data': f'pre_start:{game}:delete_bet'},
            {'text': button_texts.max_bet_button, 'callback_data': f'pre_start:{game}:max_bet'},
        ],
        [
            {'text': button_texts.top_up_balance_button, 'callback_data': f'top_up_balance'},
        ],
        [
            {'text': button_texts.back_button, 'callback_data': f'game:{game}:games_menu'},
            {'text': button_texts.press_start_game_button, 'callback_data': f'start_game'},
        ],
    ]}

    return keyboard

def not_enough_money(game: str):
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.top_up_balance_button, 'callback_data': f'top_up_balance'},
            {'text': button_texts.back_button, 'callback_data': f'game:{game}:games_menu'},
        ],
    ]}

    return keyboard

def old_friends_list_kb(bot_username, user_id, no_media=False):
    keyboard = {
        'inline_keyboard':[
        [
            {'text': '🔗 Отправить друзьям', 'url': 'tg://msg_url?url=https://t.me/{}?start={}&text=Дарю тебе ⭐️, переходи в бота и забирай!'.format(bot_username, user_id)}
        ],
    ]}

    if not no_media:
        keyboard['inline_keyboard'].append([
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],)

    return keyboard

def open_casino_kb(bot_username):
    keyboard = {'inline_keyboard':[
        [
            {'text': '💎 Хочу выиграть!', 'url': f'https://t.me/{bot_username}?start=jackpot'},
        ],
    ]}

    return keyboard

def push_notification_kb(bot_username, user_id):
    keyboard = {'inline_keyboard':[
        [
            {'text': '💎 Хочу задания!', 'callback_data': 'tasks'},
        ],
        [
            {'text': '🔗 Скопировать мою ссылочку', 'callback_data': 'get_stars'},
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}

    return keyboard


def old_friends_kb(bot_username, user_id):
    keyboard = {'inline_keyboard':[
        [
            {'text': '🔗 Отправить друзьям', 'url': 'tg://msg_url?url=https://t.me/{}?start={}&text=Дарю тебе ⭐️, переходи в бота и забирай!'.format(bot_username, user_id)}
        ],
        [
            {'text': '❗️ Список неактивных друзей', 'callback_data': 'get_inactive_users'},
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}

    return keyboard

def top_up_balance_kb(pay_url: str):
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.top_up_balance_button, 'url': pay_url},
        ],
        [
            {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
        ],
    ]}

    return keyboard

def withdrawal_moderation_kb(user_id: int, amount: int):
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.accept_moderation_withdrawal, 'callback_data': f'withrawal_admin:accept:{user_id}:{amount}'},
            {'text': button_texts.discard_moderation_withdrawal, 'callback_data': f'withrawal_admin:discard:{user_id}:{amount}'},
        ],
    ]}
    return keyboard

def withdrawal_moderation_gifts_kb(user_id: int, gift_id: str, amount: int):
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.accept_moderation_withdrawal, 'callback_data': f'withrawal_gift:accept:{user_id}:{gift_id}:{amount}'},
            {'text': button_texts.discard_moderation_withdrawal, 'callback_data': f'withrawal_gift:discard:{user_id}:{gift_id}:{amount}'},
        ],
        [
            {'text': button_texts.get_transfer_history_button, 'callback_data': f'get_transfer_history:{user_id}'}
        ],
    ]}
    return keyboard


def gift_ban_kb(user_id: int, is_banned: bool) -> dict:
    keyboard = {'inline_keyboard': [
        [
            {
                'text': button_texts.unban_user_button if is_banned else button_texts.ban_user_button,
                'callback_data': f'gift_ban:{user_id}'
            }
        ]
    ]}
    return keyboard


def admin_moderation_main_kb(is_accept: bool):
    keyboard = {'inline_keyboard':[
        [
            {'text': button_texts.accpet_withdrawal_button if is_accept else button_texts.discard_withdrawal_button, 'callback_data': f'...'},
        ],
    ]}

    return keyboard


def gifts_swiper(id1, id2, gift_id, cost):
    return {'inline_keyboard': [
    [
        {'text': '◀️', 'callback_data': f'gifts:{id1}'}, 
        {'text': '▶️', 'callback_data': f'gifts:{id2}'},
    ],
    [{'text': button_texts.buy_gift_button, 'callback_data': f'buy_gift:{gift_id}:{cost}'}],
    [
        {'text': '⬅️ В главное меню', 'callback_data': 'main_menu'},
    ],

], 'resize_keyboard': True}

def out_channel_kb(channel_url: str):
    return {'inline_keyboard': [
    [
        {'text': button_texts.sub_is_channel_button, 'url': channel_url}, 
    ],

], 'resize_keyboard': True}


def ref_admin_kb(ref_id):
     return {'inline_keyboard': [
    [
        {'text': button_texts.delete_bet_button, 'callback_data': f'referals:delete:{ref_id}'}, 
    ],

], 'resize_keyboard': True}


def admin_promocodes(promocodes: list[models.Promocode], raw: int):
    keyboard = {'inline_keyboard': []}

    raw = max(0, min(raw, len(promocodes)))
    promocodes_data = promocodes[raw:raw + 5]

    for i in promocodes_data:
        keyboard['inline_keyboard'].append([
            {
                'text': '🟢' if i.status else '❌',
                'callback_data': f'promocodes:status:{i.id}:{raw}'
            },
            {
                'text': f'🎯 {i.activated} / {i.activations}',
                'callback_data': f'...'
            },
            {
                'text': f'🗑',
                'callback_data': f'promocodes:delete:{i.id}:{raw}'
            },
        ])

    keyboard['inline_keyboard'].append([
        {'text': '➕', 'callback_data': f'promocodes:create:0:{raw}'}
    ])

    navigation_buttons = []
    if len(promocodes) > 5:
        if raw > 0:
            navigation_buttons.append({
                'text': '⬅️', 'callback_data': f'promocode_swipe:{raw - 5}'
            })
        if raw + 5 < len(promocodes):
            navigation_buttons.append({
                'text': '➡️', 'callback_data': f'promocode_swipe:{raw + 5}'
            })

    if navigation_buttons:
        keyboard['inline_keyboard'].append(navigation_buttons)

    return keyboard
