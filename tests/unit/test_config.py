# Import Settings
from app.config import Settings


# Defines a Pytest test function to verify that the application's default settings are safe
def test_defaults_are_safe():
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.gemini_api_key is None
