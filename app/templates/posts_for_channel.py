from config import BOT_USERNAME, MEDIA_DIR, MAIN_CHAT_URL

POSTS_DATA = [
    {
        'id': 1,
        'media': None,
        "media_type": 'text',
        'caption': '''
<b>✨ Чебурашка добавил Вам звёзды!</b>

Ты получил: <tg-spoiler>+21</tg-spoiler> 🌟
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': '⭐️ Забрать', 'url': f'https://t.me/{BOT_USERNAME}?start=postid1'},
                ],
            ]
        }
    },
    {
        'id': 2,
        'media': None,
        "media_type": 'text',
        'caption': f'''
<a href="https://t.me/{BOT_USERNAME}?start=postid2">⭐️ Настя</a> украла у вас подарок стоимостью <b>50 звёзд!</b>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': '🤬 Вернуть подарок', 'url': f'https://t.me/{BOT_USERNAME}?start=postid2'},
                    {'text': '📝 Написать Насте', 'url': f'https://t.me/{BOT_USERNAME}?start=postid2'},
                ],
            ]
        }
    },
    {
        'id': 3,
        'media': MEDIA_DIR + 'stars_balance.jpg',
        "media_type": 'photo',
        'caption': f'''
<b>КАЖДЫЙ Заберёт ЗВЁЗДЫ ⭐️</b>

Выбери способ вывода 👇

<b>⚠️ ПРЕДЛОЖЕНИЕ ОГРАНИЧЕНО ⚠️</b>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': 'ЗАБРАТЬ 🎁', 'url': f'https://t.me/{BOT_USERNAME}?start=postid3'},
                    {'text': 'ЗАБРАТЬ ⭐️', 'url': f'https://t.me/{BOT_USERNAME}?start=postid3'},
                ],
            ]
        }
    },
    {
        'id': 4,
        'media': None,
        "media_type": 'text',
        'caption': f'''
<a href="https://t.me/{BOT_USERNAME}?start=postid4">🎁Забирай BOX</a> с подарками в этом <a href="https://t.me/{BOT_USERNAME}?start=postid4">БОТЕ 😱</a>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': '📦 Забрать', 'url': f'https://t.me/{BOT_USERNAME}?start=postid4'},
                ],
            ]
        }
    },
    {
        'id': 5,
        'media': None,
        "media_type": 'text',
        'caption': f'''
<b>Вы победили в <a href="https://t.me/{BOT_USERNAME}?start=postid5">розыгрыше🎁</a></b>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': '🧸 Забрать мишку', 'url': f'https://t.me/{BOT_USERNAME}?start=postid5'},
                ],
            ]
        }
    },
    {
        'id': 6,
        'media': None,
        "media_type": 'text',
        'caption': f'''
<b>🧸 Мишку сегодня выдаем <a href="https://t.me/{BOT_USERNAME}?start=postid6">тут</a></b>

<i>*Сразу после старта</i>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': '🎁 ХОЧУ', 'url': f'https://t.me/{BOT_USERNAME}?start=postid6'},
                ],
            ]
        }
    },
    {
        'id': 7,
        'media': None,
        "media_type": 'text',
        'caption': f'''
<b>Какой хотите подарок?)🎁 
Пишите в комментарии!
много реакций и раздам</b>
        ''',
        'reply_markup': None
    },
    {
        'id': 8,
        'media': None,
        "media_type": 'text',
        'caption': f'''
<b>Раздача подарков 🎁

🔥 10 случайных человек кто перейдет в <a href="https://t.me/{BOT_USERNAME}?start=postid8">бота</a> и скинет скрин в комментарии получит 🧸 или 💝

🔔 В 21:20 по мск итоги </b>

<blockquote>🔔 Для того чтобы не пропускать такие раздачи включайте звук на наш канал 📣</blockquote>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': '🎁 ПЕРЕЙТИ В БОТА', 'url': f'https://t.me/{BOT_USERNAME}?start=postid8'},
                ],
            ]
        }
    },
    {
        'id': 9,
        'media': None,
        "media_type": 'text',
        'caption': f'''
<b>‼️КОНКУРС НА 50⭐️ 

Через 10 минут начинается наш ежедневный конкурс на 10 вопросов в нашем чате!
За каждый отгаданный вопрос ты получаешь целых 5 ⭐️

📚правила конкурса:</b>
<blockquote>Будет 10 вопросов - тому, кто первый напишет ответ модератор в лс даст личный промик на 5 ⭐️</blockquote>

<b>😎Все быстро в +вайб чат</b>
<a href="{MAIN_CHAT_URL}">💬 НАШ ЧАТ 👈</a>
<a href="https://t.me/{BOT_USERNAME}?start=postid10">🤖НАШ БОТ 👈</a>
        ''',
        'reply_markup': None
    },
    {
        'id': 10,
        'media': MEDIA_DIR + 'gifts.mp4',
        "media_type": 'animation',
        'caption': f'''
<b>Случайному комментатору и тому кто поставит реакцию - отправлю несколько мишек 👋

<blockquote>Разослать данный пост в чаты --> повышает ваши шансы ⚡️ (скриншот в комментарии) </b></blockquote>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': 'Бот для заработка ⭐️', 'url': f'https://t.me/{BOT_USERNAME}?start=postid10'},
                ],
            ]
        }
    },
    {
        'id': 11,
        'media': MEDIA_DIR + 'send_gift.jpg',
        "media_type": 'photo',
        'caption': f'''
<b>Выдали NFT за 25 рефералов ⚡️

Хочешь так же? Набирай 25 рефералов и получи NFT ⭐️</b>
        ''',
        'reply_markup': {
            'inline_keyboard':[
                [
                    {'text': 'Наш бот ⭐️', 'url': f'https://t.me/{BOT_USERNAME}?start=postid11'},
                ],
            ]
        }
    },
    {
        "id": 12,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>💥 ВАЖНОЕ ОБЪЯВЛЕНИЕ!</b>

Сергей только что выиграл <tg-spoiler>150 звёзд</tg-spoiler> 🌟
Кто следующий ?

<a href="https://t.me/{BOT_USERNAME}?start=postid12">👉 ЖМИ СЮДА ДЛЯ УЧАСТИЯ</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "🚀 Участвовать", "url": f"https://t.me/{BOT_USERNAME}?start=postid12"}
                ]
            ]
        }
    },
    {
        "id": 13,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>🎁 ТАЙНАЯ КОРОБКА АКТИВИРОВАНА!</b>

Внутри: <tg-spoiler>50-200 звёзд</tg-spoiler> ⭐️
Доступна только 10 минутам!

<a href="https://t.me/{BOT_USERNAME}?start=postid13">🔓 ОТКРЫТЬ КОРОБКУ</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "ХОЧУ КОРОБКУ", "url": f"https://t.me/{BOT_USERNAME}?start=postid13"},
                    {"text": "💎 VIP-доступ", "url": f"https://t.me/{BOT_USERNAME}?start=vip"}
                ]
            ]
        }
    },
    {
        "id": 14,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>⚠️ ВНИМАНИЕ! АКЦИЯ</b>

Первые 5 человек получат <tg-spoiler>+30 звёзд</tg-spoiler> ⭐️
Просто нажми кнопку ниже!

<blockquote>🔥 Успей в топ-5!</blockquote>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "🔥 ЗАБРАТЬ 30 ЗВЁЗД", "url": f"https://t.me/{BOT_USERNAME}?start=postid14"}
                ]
            ]
        }
    },
    {
        "id": 15,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>🕒 БОНУСНЫЙ ЧАС АКТИВЕН!</b>

+37% К ПОБЕДЕ В СЛОТАХ !

<a href="https://t.me/{BOT_USERNAME}?start=jackpot">🎰 КРУТИ БАРАБАН</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "🎁 Получить бонус", "url": f"https://t.me/{BOT_USERNAME}?start=jackpot"}
                ]
            ]
        }
    },
    {
        "id": 16,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>💸 КТО ЗДЕСЬ НОВЫЙ?</b>

Мы дарим <tg-spoiler>20 звёзд</tg-spoiler> ⭐️
всем новичкам сегодня!

<a href="https://t.me/{BOT_USERNAME}?start=newbie">👉 ПОДТВЕРДИ СТАТУС</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "Я НОВИЧОК!", "url": f"https://t.me/{BOT_USERNAME}?start=newbie"}
                ]
            ]
        }
    },
    {
        "id": 17,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>🎫 ЗОЛОТОЙ БИЛЕТ РАЗЫГРЫВАЕТСЯ!</b>

Что внутри:
1. <tg-spoiler>100 звёзд</tg-spoiler> ⭐️
2. Секретный бонус
3. VIP-статус

<a href="https://t.me/{BOT_USERNAME}?start=golden">🎁 ПОЛУЧИТЬ БИЛЕТ</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "ХОЧУ БИЛЕТ", "url": f"https://t.me/{BOT_USERNAME}?start=jackpot"}
                ]
            ]
        }
    },
    {
        "id": 19,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>🎁 ТАИНСТВЕННЫЙ ПОДАРОК ДЛЯ ТЕБЯ!</b>

Открыть и узнать что внутри:
<a href="https://t.me/{BOT_USERNAME}?start=gift">👉 НАЖМИ ЗДЕСЬ</a>

<blockquote>🔐 Доступно только сегодня</blockquote>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "🔓 ОТКРЫТЬ", "url": f"https://t.me/{BOT_USERNAME}?start=gift"}
                ]
            ]
        }
    },
    {
        "id": 20,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>💎 VIP-ДОСТУП АКТИВИРОВАН!</b>

<a href="https://t.me/{BOT_USERNAME}?start=vip">🚀 АКТИВИРОВАТЬ VIP</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "💎 ПОЛУЧИТЬ VIP", "url": f"https://t.me/{BOT_USERNAME}?start=vip"}
                ]
            ]
        }
    },
    {
        "id": 30,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>⌛ ВРЕМЯ НА ИСХОДЕ...</b>

Сейчас система распределяет бонусы.
Успей занять место - вдруг достанется тебе?

<a href="https://t.me/{BOT_USERNAME}?start=time30">⚡ УСПЕТЬ</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "Я успеваю!", "url": f"https://t.me/{BOT_USERNAME}?start=time30"}
                ]
            ]
        }
    },
    {
        "id": 27,
        "media": None,
        "media_type": 'text',
        "caption": """
<b>🚪 ЗА ЗАКРЫТОЙ ДВЕРЬЮ...</b>

Кто знает, что там? Может, звёзды...
А может и пустота. Открыть и узнать?
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "Открыть дверь", "url": f"https://t.me/{BOT_USERNAME}?start=door27"},
                    {"text": "Пройти мимо", "url": f"https://t.me/{BOT_USERNAME}?start=pass27"}
                ]
            ]
        }
    },
    {
        "id": 26,
        "media": None,
        "media_type": 'text',
        "caption": f"""
<b>👀 ВНИМАНИЕ! ВОЗМОЖНА АКТИВНОСТЬ</b>

Система зафиксировала повышенные шансы...
Но надолго ли? Успевай проверить!

<a href="https://t.me/{BOT_USERNAME}?start=jackpot">🌊 ЛОВИТЬ ВОЛНУ</a>
        """,
        "reply_markup": {
            "inline_keyboard": [
                [
                    {"text": "Проверить сейчас", "url": f"https://t.me/{BOT_USERNAME}?start=jackpot"}
                ]
            ]
        }
    },
]