# LinkedIn launch post — draft

Two versions below. Pick one, tweak, post.

---

## Version A — problem-led (recommended)

**Why agent identity is broken today (and what I built to fix it)**

Most production AI agents I've seen ship in one of two shapes:

1. The agent holds a long-lived API key with access to every internal tool.
2. The agent authenticates as itself, so every audit log just says "the bot did it."

Neither survives a SOC 2 audit. Neither gives a security team a kill switch.

I spent the last few weekends building [agent-identity-broker](https://github.com/anurag27397/agent-identity-broker), a runnable counter-example. The idea is OAuth 2.1 token exchange (RFC 8693) applied to LLM agents:

- The human user authenticates once (OIDC).
- The broker issues a 1-hour session JWT bound to that user.
- Before each tool call, the agent asks the broker for a 60-second scoped token for one specific tool and one specific scope.
- Every event is audited with stable session_id and jti correlation.
- The operator has one click to revoke a session or kill all minting globally.

The repo runs end-to-end with `docker compose up`. There's a Claude agent that calls three mock tools through the broker. The dashboard updates live as the agent works, and you can revoke its session mid-conversation and watch the next tool call fail cleanly.

This is the pattern I think most companies will end up at once they move past the "give it a god key" phase. The repo is for anyone wiring up production agents and looking for a concrete starting point on the identity side.

Repo + architecture notes (threat model, prod roadmap):
https://github.com/anurag27397/agent-identity-broker

Happy to swap notes with anyone building in this space.

---

## Version B — short and pointed

I've been seeing the same pattern in every production AI-agent system I look at: one long-lived API key, full access to every tool, no useful audit trail, no kill switch. It's the prompt-injection equivalent of running production as root.

I built a working example of what proper agent identity looks like:

→ https://github.com/anurag27397/agent-identity-broker

Three takeaways from the build:

1. The unit of authorization is not "the agent" or "the user." It's the user + session + scope + 60-second window. Every tool call gets its own token.
2. `jti` is the missing primitive. Without it you cannot correlate "the broker minted X" with "the tool was called with X" in an audit.
3. The kill switch matters more than you think. The first time something looks wrong at 2 AM, you want one button that stops all minting globally.

Sequence diagrams, threat model, and the production roadmap are in ARCHITECTURE.md. Feedback welcome.

---

## Tags to consider

`#AISecurity` `#IAM` `#IdentityGovernance` `#LLMSecurity` `#PromptInjection` `#OAuth` `#ClaudeCode` `#Anthropic`

## Companion image ideas

- Screenshot of the live dashboard with the audit chain visible (login → mint → tool_call → denied) — most powerful single image
- The architecture diagram from ARCHITECTURE.md
- A short Loom of the agent + dashboard side by side, including a revoke action mid-conversation

## When to post

Tuesday or Wednesday, 9–10 AM Pacific. Reach is meaningfully better midweek-morning than weekend or evening.

## What to do in the first 24 hours

- Reply to every substantive comment within 4 hours.
- Don't argue with hot takes. Engage with the technical ones; ignore the rest.
- Pin the repo link as the first comment if LinkedIn deprioritizes the original link.
