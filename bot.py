import asyncio
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = "8516580775:AAGal4FIUfn-Y822L0YX_LAi6pyBjUIIDT4"

# username бота БЕЗ @
BOT_USERNAME = "FriendPortal_bot"

# ссылка на mini app, если нужна обычная fallback-ссылка
MINI_APP_URL = "https://friendportal-backend-1.onrender.com/index.html"

dp = Dispatcher()


def build_open_app_keyboard(start_param: str | None = None) -> InlineKeyboardMarkup:
    if start_param:
        webapp_link = f"https://t.me/{BOT_USERNAME}/app?startapp={start_param}"
    else:
        webapp_link = f"https://t.me/{BOT_USERNAME}/app"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🚀 Open App",
                    web_app={"url": MINI_APP_URL}
                )
            ]
        ]
    )


@dp.message(CommandStart(deep_link=True))
async def start_with_param(message: Message):
    raw = message.text or ""
    parts = raw.split(maxsplit=1)
    param = parts[1].strip() if len(parts) > 1 else None

    text = (
        "FriendPortal is a TON-based referral & advertising mini app.\n\n"
        "💎 Earn TON by inviting users\n"
        "📊 Live balance & referral statistics\n"
        "💸 Fast withdrawals after activation\n"
        "📣 Promote your project to a crypto-native audience\n"
        "🛠 Custom Telegram Mini App development available\n\n"
        "👉 Tap the button below to open the app"
    )

    await message.answer(
        text,
        reply_markup=build_open_app_keyboard(param)
    )


@dp.message(CommandStart())
async def start_plain(message: Message):
    text = (
        "FriendPortal is a TON-based referral & advertising mini app.\n\n"
        "💎 Earn TON by inviting users\n"
        "📊 Live balance & referral statistics\n"
        "💸 Fast withdrawals after activation\n"
        "📣 Promote your project to a crypto-native audience\n"
        "🛠 Custom Telegram Mini App development available\n\n"
        "👉 Tap the button below to open the app"
    )

    await message.answer(
        text,
        reply_markup=build_open_app_keyboard()
    )


@dp.message(F.text == "/app")
async def app_command(message: Message):
    await message.answer(
        "Open FriendPortal:",
        reply_markup=build_open_app_keyboard()
    )


async def main():
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
