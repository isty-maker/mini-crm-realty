import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Ensure pytest-django plugin is available for the test session."""
    if not config.pluginmanager.hasplugin("django"):
        raise RuntimeError(
            "pytest-django не установлен. Установите dev-зависимости:\n"
            "    pip install -r requirements.txt -r requirements-dev.txt\n"
        )
