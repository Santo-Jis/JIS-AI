"""
Configuration - সব সেটিংস এক জায়গায়
.env ফাইল থেকে পড়ে
"""

from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Anthropic
    ANTHROPIC_API_KEY: str = "your-anthropic-api-key"

    # WhatsApp Business API (Meta)
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    WHATSAPP_VERIFY_TOKEN: str = "my_secret_verify_token"

    # App
    SECRET_KEY: str = "change-this-secret-key"
    DEBUG: bool = True
    PORT: int = 8000

    class Config:
        env_file = ".env"

settings = Settings()
