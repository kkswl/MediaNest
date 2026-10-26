import pytest

from app.adapters import ReadError
from scripts.verify_scoped import Budget


def test_durable_budget_survives_restart_and_rejects_scope_changes(tmp_path):
    path = tmp_path / "run.json"
    budget = Budget(path, 1, 2)
    budget.reserve("directory")
    restarted = Budget(path, 1, 2)
    restarted.reserve("directory")
    with pytest.raises(ReadError):
        restarted.reserve("directory")
    restarted.reserve("health")
    with pytest.raises(ReadError):
        restarted.reserve("health")
    with pytest.raises(ValueError):
        Budget(path, 1, 3)
    assert restarted.read()["directory"] == 2
    restarted.update(stopped=True)
    with pytest.raises(ReadError):
        restarted.reserve("health")
