"""Role -> scope policy for the demo.

Hardcoded for clarity. A real broker would load this from a policy store
(OPA, Cedar, a database). For the demo the point is to show what the
broker decides, not where the decision lives.
"""


# Which scopes each tool accepts.
TOOL_SCOPES: dict[str, set[str]] = {
    "customer-data": {"customer-data:read", "customer-data:write"},
    "finance-data": {"finance-data:read", "finance-data:write"},
    "email-send": {"email-send"},
}


# Which scopes each role is allowed to mint.
ROLE_SCOPES: dict[str, set[str]] = {
    "analyst": {
        "customer-data:read",
        "finance-data:read",
    },
    "admin": {
        "customer-data:read",
        "customer-data:write",
        "finance-data:read",
        "finance-data:write",
        "email-send",
    },
}


class PolicyDecision:
    __slots__ = ("allowed", "reason")

    def __init__(self, allowed: bool, reason: str):
        self.allowed = allowed
        self.reason = reason

    def __repr__(self) -> str:
        return f"PolicyDecision(allowed={self.allowed}, reason={self.reason!r})"


def allowed_scopes(roles: list[str]) -> set[str]:
    out: set[str] = set()
    for role in roles:
        out.update(ROLE_SCOPES.get(role, set()))
    return out


def evaluate(*, roles: list[str], audience: str, scope: str) -> PolicyDecision:
    if audience not in TOOL_SCOPES:
        return PolicyDecision(False, f"unknown audience {audience!r}")
    if scope not in TOOL_SCOPES[audience]:
        return PolicyDecision(
            False,
            f"scope {scope!r} not accepted by audience {audience!r}",
        )
    if scope not in allowed_scopes(roles):
        return PolicyDecision(
            False,
            f"scope {scope!r} not granted to roles {roles!r}",
        )
    return PolicyDecision(True, "ok")
