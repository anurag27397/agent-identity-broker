import pytest

from audit import (
    LOGIN,
    SCOPED_DENIED,
    SCOPED_MINTED,
    TOOL_CALL,
    AuditStore,
)


@pytest.fixture
def store(tmp_path):
    return AuditStore(str(tmp_path / "audit.db"))


def test_record_and_query_by_session(store):
    store.record(
        event_type=LOGIN,
        actor_sub="u1",
        actor_username="alice",
        session_id="sess-1",
    )
    store.record(
        event_type=SCOPED_MINTED,
        actor_sub="u1",
        actor_username="alice",
        session_id="sess-1",
        jti="jti-1",
        audience="customer-data",
        scope="customer-data:read",
    )
    events = store.events_for_session("sess-1")
    assert len(events) == 2
    types = {e["event_type"] for e in events}
    assert types == {LOGIN, SCOPED_MINTED}


def test_recent_sessions_aggregates_counters(store):
    store.record(event_type=LOGIN, session_id="s1", actor_username="alice")
    store.record(event_type=SCOPED_MINTED, session_id="s1", jti="j1")
    store.record(event_type=TOOL_CALL, session_id="s1", jti="j1")
    store.record(
        event_type=SCOPED_DENIED, session_id="s1", reason="not granted"
    )
    store.record(event_type=LOGIN, session_id="s2", actor_username="bob")

    sessions = store.recent_sessions()
    by_id = {s["session_id"]: s for s in sessions}
    assert by_id["s1"]["event_count"] == 4
    assert by_id["s1"]["tool_calls"] == 1
    assert by_id["s1"]["denials"] == 1
    assert by_id["s2"]["event_count"] == 1


def test_recent_sessions_orders_by_last_event(store):
    import time

    store.record(event_type=LOGIN, session_id="oldest")
    time.sleep(0.01)
    store.record(event_type=LOGIN, session_id="middle")
    time.sleep(0.01)
    store.record(event_type=LOGIN, session_id="newest")

    sessions = store.recent_sessions()
    order = [s["session_id"] for s in sessions]
    assert order.index("newest") < order.index("middle") < order.index("oldest")


def test_events_ordered_desc(store):
    for i in range(5):
        store.record(event_type=LOGIN, session_id="s", metadata={"i": i})

    events = store.events_for_session("s")
    ids = [e["id"] for e in events]
    assert ids == sorted(ids, reverse=True)
