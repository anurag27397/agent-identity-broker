from policy import allowed_scopes, evaluate


def test_analyst_can_read_customer_data():
    decision = evaluate(
        roles=["analyst"], audience="customer-data", scope="customer-data:read"
    )
    assert decision.allowed, decision.reason


def test_analyst_can_read_finance_data():
    decision = evaluate(
        roles=["analyst"], audience="finance-data", scope="finance-data:read"
    )
    assert decision.allowed, decision.reason


def test_analyst_cannot_send_email():
    decision = evaluate(roles=["analyst"], audience="email-send", scope="email-send")
    assert not decision.allowed
    assert "not granted" in decision.reason


def test_analyst_cannot_write_customer_data():
    decision = evaluate(
        roles=["analyst"], audience="customer-data", scope="customer-data:write"
    )
    assert not decision.allowed


def test_admin_can_send_email():
    decision = evaluate(roles=["admin"], audience="email-send", scope="email-send")
    assert decision.allowed, decision.reason


def test_unknown_audience_rejected():
    decision = evaluate(
        roles=["admin"], audience="something-else", scope="something:read"
    )
    assert not decision.allowed
    assert "unknown audience" in decision.reason


def test_scope_must_match_audience():
    # asking customer-data tool for a finance-data scope makes no sense
    decision = evaluate(
        roles=["analyst"], audience="customer-data", scope="finance-data:read"
    )
    assert not decision.allowed
    assert "not accepted by audience" in decision.reason


def test_no_roles_yields_empty_scopes():
    assert allowed_scopes([]) == set()


def test_multiple_roles_union():
    scopes = allowed_scopes(["analyst", "admin"])
    assert "customer-data:read" in scopes
    assert "email-send" in scopes
