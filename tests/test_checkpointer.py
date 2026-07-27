"""Tests for the SQLite-backed checkpointer implementation."""
import pytest
from sqlalchemy import Engine, create_engine

# Ensure models are imported so the Base metadata contains Checkpoint
from app.db.models import Base  # noqa: F401
from app.db.checkpointer import SqliteCheckpointer


@pytest.fixture
def engine() -> Engine:
    """Provide an in-memory SQLite engine with the required tables."""
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def checkpointer(engine: Engine) -> SqliteCheckpointer:
    """Provide a SqliteCheckpointer using the test engine."""
    return SqliteCheckpointer(engine=engine)


def test_save_and_retrieve(checkpointer):
    """Test saving and retrieving a checkpoint state."""
    config = {"configurable": {"thread_id": "test-thread"}}
    fnode_id = "classify_intent"
    state = {
        "tenant_id": "tenant1",
        "wa_number": "+1234567890",
        "message_text": "hello",
        "timestamp": "2024-01-01T00:00:00",
        "intent": "greet",
        "confidence": 0.95,
    }

    checkpointer.save(config, fnode_id, state)
    retrieved = checkpointer.get(config, fnode_id)
    assert retrieved is not None
    assert retrieved["tenant_id"] == "tenant1"
    assert retrieved["intent"] == "greet"
    assert retrieved["confidence"] == 0.95

    # Different fnode_id should return None
    assert checkpointer.get(config, "other_node") is None


def test_overwrite_checkpoint(checkpointer):
    """Test that saving again overwrites the existing checkpoint."""
    config = {"configurable": {"thread_id": "another-thread"}}
    fnode_id = "lookup_catalog"
    state_v1 = {"version": 1}
    state_v2 = {"version": 2}

    checkpointer.save(config, fnode_id, state_v1)
    assert checkpointer.get(config, fnode_id)["version"] == 1

    checkpointer.save(config, fnode_id, state_v2)
    assert checkpointer.get(config, fnode_id)["version"] == 2


def test_multiple_threads(checkpointer):
    """Different thread IDs store independently."""
    config1 = {"configurable": {"thread_id": "thread-1"}}
    config2 = {"configurable": {"thread_id": "thread-2"}}
    fnode_id = "compose_reply"

    checkpointer.save(config1, fnode_id, {"msg": "state1"})
    checkpointer.save(config2, fnode_id, {"msg": "state2"})

    assert checkpointer.get(config1, fnode_id)["msg"] == "state1"
    assert checkpointer.get(config2, fnode_id)["msg"] == "state2"


def test_get_missing_returns_none(checkpointer):
    """Missing checkpoint returns None (no exception)."""
    config = {"configurable": {"thread_id": "no-such-thread"}}
    assert checkpointer.get(config, "any_node") is None