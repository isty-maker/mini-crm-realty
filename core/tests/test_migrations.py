from pathlib import Path


def test_single_initial_migration_only():
    migration_dir = Path(__file__).resolve().parent.parent / "mig_current"
    migration_files = sorted(
        f.name for f in migration_dir.glob("*.py") if f.name != "__init__.py"
    )
    found = ", ".join(migration_files) if migration_files else "none"
    assert migration_files == ["0001_initial.py"], (
        "Expected only '0001_initial.py' migration in core.mig_current, "
        f"found: {found}"
    )
