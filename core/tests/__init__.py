# Ensure Django is set up before some tests import project code under manage.py test
# (Django's DiscoverRunner sets this up; this is a no-op safety net.)
try:
    import django  # noqa: F401
except Exception:
    pass
