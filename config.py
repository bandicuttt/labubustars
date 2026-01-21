import os
from dotenv import load_dotenv
from typing import Dict, Tuple, Optional
load_dotenv()


BOT_TOKEN = os.getenv('BOT_TOKEN', '8325279009')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'bear_free_bot')
ADMINS = list(map(int, os.getenv('ADMINS', '452341151').split(',')))
SKIP_UPDATES = os.getenv('SKIP_UPDATES', 'True').lower() == 'true'
PLANEAPP_URL = os.getenv('PLANEAPP_URL', 'https://google.com')
PLANEAPP_SIGN_SECRET = os.getenv('PLANEAPP_SIGN_SECRET', BOT_TOKEN)
PLANEAPP_LINK_TTL_SECONDS = int(os.getenv('PLANEAPP_LINK_TTL_SECONDS', '900'))
ADSGRAM_BLOCK_ID = os.getenv('ADSGRAM_BLOCK_ID', '')
# SUBSCRIBES & TASKS
FLYER_API_KEY = os.getenv('FLYER_API_KEY', 'FL-ZmHMm')
SUBGRAM_API_KEY = os.getenv('SUBGRAM_API_KEY', '')
TGRASS_API_KEY = "7540951a922d47e09ebebe01c7d23497"
USE_SUBGRAM_HOOK = os.getenv('SKIP_UPDATES', 'True').lower() == 'true'
FAST_API_HOST=os.getenv('FAST_API_HOST', '0.0.0.0')
FAST_API_PORT=int(os.getenv('FAST_API_PORT', '8000'))
GRAMADS_API_KEY = os.getenv('GRAMADS_API_KEY', '')
BOTOHUB_API_URL = "https://botohub.me/get-tasks"
BOTOHUB_API_TOKEN = "6a681e3d-8494-43f7-aea1-d7e50383cd3b"
BOTOHUB_COOLDOWN = 60*60

GIFTLY_API_TOKEN = "giftlyaup7sa1myh655dnr71p9p9tdq"
DARTS_GIFT_ID = "5170233102089322756"

TIMEZONE = os.getenv('TIMEZONE', 'UTC')

# DEBUG MODE
DEBUG_MODE = os.getenv('DEBUG_MODE', 'True').lower() == 'true'
PG_DEBUG_MODE = os.getenv('PG_DEBUG_MODE', 'False').lower() == 'true'
REDIS_DEBUG_MODE = os.getenv('REDIS_DEBUG_MODE', 'False').lower() == 'true'

# PG
POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'root')
POSTGRES_DB = os.getenv('POSTGRES_DB', 'podarkiebot')
POSTGRES_PORT = int(os.getenv('POSTGRES_PORT', '5432'))
POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')

# REDIS
REDIS_DB = int(os.getenv('REDIS_DB', '1'))
REDIS_JOBSTORE_DB = int(os.getenv('REDIS_JOBSTORE_DB', '2'))
REDIS_PORT = int(os.getenv('REDIS_PORT', '6379'))
REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')

# OTHER
ADS_COOLDOWN = 48*60*60
WAIT_STICKER_ID = os.getenv('WAIT_STICKER_ID', 'CAACAgIAAxkBAAIsV2iSiAfOaDazLXOb8GZYUomTap7HAAKAagACFHeQSvaGlXBvr7PnNgQ')
MEDIA_DIR = os.getenv('MEDIA_DIR', 'temp/')
REF_STARS_COUNT = int(os.getenv('REF_STARS_COUNT', '3'))
CLICKER_GAME_REWARD = float(os.getenv('CLICKER_GAME_REWARD', '0.1'))
CLICKER_GAME_RELOAD_TIME = int(os.getenv('CLICKER_GAME_RELOAD_TIME', '10'))
DAILY_GAME_REWARD = int(os.getenv('DAILY_GAME_REWARD', '1'))
DAILY_GAME_REWARD_TIME = int(os.getenv('DAILY_GAME_REWARD_TIME', str(24*60*60)))
FAQ_URL = os.getenv('FAQ_URL', 'https://t.me/patrickstarsfarm/14')
MIN_FRIENDS_FOR_WITHDRAWAL = int(os.getenv('MIN_FRIENDS_FOR_WITHDRAWAL', '5'))
REVIEWS_CHANNEL_URL = os.getenv('REVIEWS_CHANNEL_URL', 'https://t.me/bandicuttt')
REVIEWS_CHANNEL_ID = int(os.getenv('REVIEWS_CHANNEL_ID', '-1002951149634'))
MAIN_CHANNEL_URL = os.getenv('MAIN_CHANNEL_URL', 'https://t.me/patrickstars_chat')
MAIN_CHANNEL_ID = int(os.getenv('MAIN_CHANNEL_ID', '452341151'))
MAIN_CHAT_URL = os.getenv('MAIN_CHAT_URL', 'https://t.me/patrickstars_chat')
MAIN_CHAT_ID = int(os.getenv('MAIN_CHAT_ID', '452341151'))
SUPPORT_USERNAME = os.getenv('SUPPORT_USERNAME', '@bandicuttt')
MODERTAION_CHAT_ID = int(os.getenv('MODERTAION_CHAT_ID', '452341151'))
COST_PER_TASK = float(os.getenv('COST_PER_TASK', '0.25'))
LOTTERY_TTL = int(os.getenv('LOTTERY_TTL', '60'))
LOTTERY_TICKET_PRICE = int(os.getenv('LOTTERY_TICKET_PRICE', '10'))
LOTTERY_MIN_USERS = int(os.getenv('LOTTERY_MIN_USERS', '3'))

# Конфигурация капчи
CaptchaData = Tuple[str, str, int]  # (answer, token, message_id)
ActiveCaptchas = Dict[int, CaptchaData]
CAPTCHA_SYMBOLS = ['❤️', '💎', '🎁', '⭐️', '💰', '🎟']
CAPTCHA_LENGTH = 7
CAPTCHA_SUM = 5

# ОП
MAX_OP = 4
OP_TTL = 60*60*5

# Конфигурация медиа
LOADING_ID = 'AgACAgIAAxkBAAF-2YdpUca0NWPyfWOgg4T3NlXmy9KQmwACfw9rG4c7iEoX0uYra5bjPwEAAwIAA3gAAzYE'
MAIN_MENU_ID = 'AgACAgIAAxkBAAF-2YVpUcahE7gslZh4LT4jkthdUMod3gACbw9rG4c7iEoUQO8154frJAEAAwIAA3gAAzYE'
DEPOSIT_MENU_ID = 'AgACAgIAAxkBAAF-2YtpUcbcnaqokQsBN1xrWylHZLsMDAACkA9rG4c7iEoIiQ1rPplJZwEAAwIAA3kAAzYE'
GAMES_MENU_ID = 'AgACAgIAAxkBAAO2aVE5YqUKk_q5gFap5z9AwDFIKqsAApAPaxuHO4hKJZzSU_ROyBsBAAMCAAN5AAM2BA'
GET_STARS_MENU_ID = 'AgACAgIAAxkBAAF-2YtpUcbcnaqokQsBN1xrWylHZLsMDAACkA9rG4c7iEoIiQ1rPplJZwEAAwIAA3kAAzYE'
INSTRUCTION_MENU_ID = 'AgACAgIAAxkBAAF-2YFpUcZxtbvodAi2U2k1MgIQSuv_cAACjQ9rG4c7iEo1cQcK2LVfewEAAwIAA3gAAzYE'
OLD_FRIENDS_MAIN_MENU_ID = 'AgACAgIAAxkBAAF-2Y9pUccU0k7C4dCgdLNK3fcntLVhegACjw9rG4c7iEomb2m0CYsxKgEAAwIAA3kAAzYE'
PROFILE_MAIN_MENU_ID = 'AgACAgIAAxkBAAF-2YVpUcahE7gslZh4LT4jkthdUMod3gACbw9rG4c7iEoUQO8154frJAEAAwIAA3gAAzYE'
TASKS_MAIN_MENU_ID = 'AgACAgIAAxkBAAF-2YNpUcaH1JWHcCdRHeWJjaLprUHwLgACiw9rG4c7iEptUqyMzanW-QEAAwIAA3gAAzYE'
TOP_MAIN_MENU_ID = 'AgACAgIAAxkBAAF-2Y1pUccAAR3z0N6DWsvmBtnsI_E3BBMAAocPaxuHO4hKpQrIx_pCKioBAAMCAAN5AAM2BA'
WITHDRAWAL_MAIN_MENU_ID = 'AgACAgIAAxkBAAF-2YlpUcbGd_IDJ-Z_N4UKFbyimqeulAACgA9rG4c7iErtihGGqy0JRgEAAwIAA3kAAzYE'
SUBSCRIBE_PHOTO_ID = 'AgACAgIAAxkBAAGfwpppapWNx46i8AeCFh40ab6ks978nwACNhJrG4AiUUvriiiIVKEz3wEAAwIAA3gAAzgE'
FISHING_PHOTO_ID = 'AgACAgIAAxkBAAGfyKRpaqdhkP6jOohKItnbSB6p65rSawACtRJrG4AiUUtDDVU5iIMZVgEAAwIAA3gAAzgE'

