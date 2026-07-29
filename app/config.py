from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    BOT_TOKEN: str
    ADMIN_CHAT_ID: int  # -100...
    DB_PATH: str = "bot.db"
    CRYPTO_BOT_TOKEN: str  # токен из @CryptoBot -> /pay -> Create App
    CRYPTO_BOT_IS_MAINNET: bool = True  # False для @CryptoTestnetBot
    PROXY_URL: Optional[str] = None  # например http://127.0.0.1:1080 или socks5://...
    PROXY_URL_CRYPTO: Optional[str] = None  # отдельный прокси для CryptoBot если нужно

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
