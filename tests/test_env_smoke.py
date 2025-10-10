import pytest


def test_pytest_django_plugin_loaded(pytestconfig: pytest.Config) -> None:
    assert pytestconfig.pluginmanager.hasplugin(
        "django"
    ), "Плагин pytest-django не подхватился — проверьте установку dev-зависимостей"


def test_settings_module_present(settings) -> None:  # type: ignore[no-untyped-def]
    assert hasattr(settings, "INSTALLED_APPS")
