from pydantic_settings import BaseSettings

class AISettings(BaseSettings):
    OPENAI_API_KEY: str = ""
    # Add other provider keys here if needed, e.g. ANTHROPIC_API_KEY

    class Config:
        env_file = ".env"
        extra = "ignore"

ai_settings = AISettings()
