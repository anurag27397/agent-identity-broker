import pytest

from revocation import RevocationStore


@pytest.fixture
def rev(tmp_path):
    return RevocationStore(str(tmp_path / "audit.db"))


def test_session_not_revoked_by_default(rev):
    assert rev.is_revoked("any-session") is False


def test_revoke_and_check(rev):
    rev.revoke_session("sess-1", revoked_by="op", reason="explicit")
    assert rev.is_revoked("sess-1") is True
    assert rev.is_revoked("sess-2") is False


def test_revoke_is_idempotent(rev):
    rev.revoke_session("sess-1")
    rev.revoke_session("sess-1", reason="updated reason")
    assert rev.is_revoked("sess-1") is True
    assert "sess-1" in rev.list_revoked()


def test_unrevoke(rev):
    rev.revoke_session("sess-1")
    assert rev.unrevoke_session("sess-1") is True
    assert rev.is_revoked("sess-1") is False
    # second unrevoke is a no-op
    assert rev.unrevoke_session("sess-1") is False


def test_kill_switch_default_off(rev):
    assert rev.is_kill_switch_on() is False
    assert rev.kill_switch_state() == {"engaged": False}


def test_kill_switch_engage_and_disengage(rev):
    rev.engage_kill_switch()
    assert rev.is_kill_switch_on() is True
    assert rev.kill_switch_state() == {"engaged": True}

    rev.disengage_kill_switch()
    assert rev.is_kill_switch_on() is False


def test_kill_switch_engage_is_idempotent(rev):
    rev.engage_kill_switch()
    rev.engage_kill_switch()
    assert rev.is_kill_switch_on() is True


def test_list_revoked_returns_set(rev):
    rev.revoke_session("a")
    rev.revoke_session("b")
    rev.revoke_session("c")
    rev.unrevoke_session("b")
    assert rev.list_revoked() == {"a", "c"}
