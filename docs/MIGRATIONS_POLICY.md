# Core migrations policy

- The `core` app keeps a single snapshot migration: `core/migrations/0001_initial.py`.
- Feature branches SHOULD NOT add new migration files. Update `core/models.py` freely, then regenerate the snapshot before merging to `main`.
- CI fails if more than one migration file for `core` exists or if pending migrations are detected.
- After pulling latest changes locally, run `python manage.py reset_dev_db` to rebuild the SQLite dev database (this deletes local data).
