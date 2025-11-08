
from pydantic import BaseSettings
class Settings(BaseSettings):
    TELEGRAM_BOT_TOKEN: str = ''
    DATABASE_URL: str = ''
    REDIS_URL: str = ''
    ADMIN_API_KEY: str = 'changeme'
    class Config:
        env_file = '.env'
settings = Settings()
