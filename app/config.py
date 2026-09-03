from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int  # -100...
    DB_PATH: str = "bot.db"
    CRYPTO_BOT_TOKEN: str  # токен из @CryptoBot -> /pay -> Create App
    CRYPTO_BOT_IS_MAINNET: bool = True  # False для @CryptoTestnetBot
    PROXY_URL: Optional[str] = None  # например http://127.0.0.1:1080 или socks5://...
    PROXY_URL_CRYPTO: Optional[str] = None  # отдельный прокси для CryptoBot если нужно

    # Фоновый опрос неоплаченных счетов в CryptoBot (секунды). 0 = выключить.
    INVOICE_POLL_INTERVAL: int = 60
    # Логировать все входящие апдейты (отладочный роутер). В проде держим выключенным.
    DEBUG_ALL: bool = False

    # pydantic v2: class Config устарел и давал DeprecationWarning при старте.
    # extra="ignore" — чтобы лишние переменные в .env не роняли бота.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
