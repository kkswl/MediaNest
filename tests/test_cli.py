"""CLI diagnostics must describe the actual isolated database, not a stale constant."""

import sys

from sqlalchemy import select

from app.cli import main
from app.db import SchemaMigration


def test_migrate_prints_actual_database_version(environment, monkeypatch, capsys):
    database, settings, readers, worker, _ids = environment
    monkeypatch.setattr("app.cli.context", lambda: (database, settings, readers, worker))
    monkeypatch.setattr(sys, "argv", ["medianest", "migrate"])
    main()
    assert "当前版本为 3" in capsys.readouterr().out
    # A future additive migration must not require another diagnostic string edit.
    with database.session.begin() as db:
        db.add(SchemaMigration(version=4))
    main()
    assert "当前版本为 4" in capsys.readouterr().out
    with database.session() as db:
        assert list(db.scalars(select(SchemaMigration.version).order_by(SchemaMigration.version))) == [1, 2, 3, 4]
