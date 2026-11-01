# Import Settings
from app.config import Settings


# Defines a Pytest test function to verify that the application's default settings are safe
def test_defaults_are_safe():
    settings = Settings(_env_file=None)
    assert settings.app_env == "development"
    assert settings.gemini_api_key is None


def test_database_path_defaults_to_local_sqlite_file():
    settings = Settings(_env_file=None)
    assert settings.database_path == "data/app.sqlite3"
