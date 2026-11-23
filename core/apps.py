from django.apps import AppConfig

_AUTO_MIGRATED = False


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        global _AUTO_MIGRATED
        if _AUTO_MIGRATED:
            return
        try:
            from .utils.auto_migrate import auto_migrate_once_if_needed
            auto_migrate_once_if_needed()
            _AUTO_MIGRATED = True
        except Exception:
            # never fail app loading because of auto-migrate
            pass
