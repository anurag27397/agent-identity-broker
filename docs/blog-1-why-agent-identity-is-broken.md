# Why agent identity is broken today

*Draft 1, May 2026. Edit the personal-experience bits before posting. Anywhere I wrote "three of the four startups I consulted with," or "last quarter I sat in on a review," etc., is a placeholder for your own real story. The argument and the technical claims hold regardless.*

---

Last quarter I sat in on a SOC 2 review where the auditor pointed at a destructive change in the production database and asked who made it. The team's runbook said the change came from an internal Claude assistant, so the technically-correct answer was "the bot." That was acceptable to nobody in the room, including the engineer who had clearly prompted the bot into doing it.

This is now a normal conversation. I've had it three times this year with three different clients. All of them shipped AI agents to internal users in 2025 and all of them ended up in the same place: nobody can answer the question "who actually did this thing."

There are two patterns I keep seeing.

The first is what you'd build on a Friday afternoon when leadership wants a demo on Monday. You give the agent one long-lived API key with access to every tool. It works. It demos great. It survives until the first time someone in a corporate Slack realizes they can paste a prompt into the agent that pulls every customer record out of Salesforce. (Three of the four AI agent rollouts I reviewed this year shipped exactly this pattern to production. One of them had a compliance team. They didn't catch it either.)

The second is more sophisticated. The agent authenticates as itself, usually as a service account or a dedicated OAuth client, and the tools all trust that identity. This is better in the sense that the agent's credential can be rotated. It's worse in the sense that every action in the audit log is now attributed to one machine identity, regardless of which human caused it. SOX auditors hate this. SOC 2 auditors hate this. The people on your security team who triage incidents at 2 AM hate it most of all, because they cannot revoke one user's access without revoking the agent for everyone.

Neither of these is going to survive contact with a serious security review.

## What's broken, specifically

The mismatch is between how AI agents are designed and how identity systems were designed.

A modern IdP (Okta, Auth0, Keycloak, SailPoint if you grew up in big enterprise) assumes a stable principal. A person logs in. Claims get put in a token. That token represents that person for the duration of a session. The audit log says "this principal did this thing at this time." Standard stuff, and it's worked for fifteen years.

An AI agent breaks every assumption in that sentence. The principal isn't stable; the agent acts on behalf of whoever is talking to it right now. Claims about "the user" are correct only for one turn of one conversation. And the actions the agent takes aren't its own. They're delegated. The agent is not a principal. It's an actor.

OAuth has had a word for this since 2020, when RFC 8693 became a published standard. The idea is straightforward: you have a primary subject (the human), you have an actor (the agent), and tokens can carry both. The user authenticates once. The agent gets a token that says "I am acting on behalf of this user, with this scope, for this short window." When the actor changes, or the scope changes, you mint a new token.

This is the right primitive. It's also almost never implemented in AI agent code today, including in the official sample code from any of the model vendors I can think of.

## What people actually need

Three things, from sitting in too many of these reviews.

One. Every tool call needs to be attributable to a specific human user. Not "the bot." Not "the agent service account." The actual person whose conversation produced the action. If your GRC team can't answer who-did-what for an autonomous action, you have a real problem regardless of what your token framework looks like.

Two. The agent's blast radius needs to be bounded per call, not per session. The whole point of giving an agent powerful tools is that you don't want to manually approve each action. "Not manually approving" doesn't have to mean "the agent gets to do anything its current credentials allow." It can mean "the agent gets exactly the permission it needs for the next sixty seconds, and the credential it holds proves nothing else." Time-bound and scope-bound, every call.

Three. The operator needs a kill switch that works fast. The first time something looks wrong at 2 AM, you want one button that stops the agent from doing more damage, without taking down whatever humans are still working. Today, in most agent codebases I've reviewed, "kill switch" means "restart the agent service" or "rotate the API key and pray." Neither of these scales to a real organization.

## The pattern that works

You need a small broker between the agent and your tools.

The broker holds the trust relationship with your IdP. When a user authenticates, the broker mints a session token bound to that user. The agent holds that token. Before every single tool call, the agent calls the broker and says "this user wants me to invoke this tool with this scope." The broker checks policy. Does this user's role allow this scope? Has the session been revoked? Is the broker in kill-switch mode? If everything passes, it mints a short-lived token, sixty seconds is plenty, with the target tool as the audience and the requested scope as a claim. If anything fails, it returns a denial with a reason the agent can pass back into the conversation.

The tool sees a regular OAuth-style Bearer token. It validates the signature against the broker's JWKS, checks that the `aud` matches its own ID, and serves the request. Every step gets logged with a stable `session_id` and a per-token `jti`, so a single audit query can answer "what did this conversation actually do, from login through last tool call."

None of this is novel. The exchange flow is RFC 8693, sixteen pages long, easy to read. The audit pattern is what every halfway-mature SaaS company already does for their own internal APIs. The novelty is recognizing that an AI agent is not a service account. It's an actor. It needs to be wired into the same identity story you've spent ten years building for your humans.

## What's hard

A few things are genuinely hard, and I want to name them so this doesn't read like a sales pitch.

Replay is the obvious one. Short-lived tokens limit damage but don't prevent it within their window. The right answer is per-tool replay caches keyed by `jti`, which means you need fast shared storage and you need every tool to do the check. Most teams won't, and you'll have to be honest about that in your threat model.

Prompt injection is the harder one. If a malicious input convinces the agent to ask the broker for a scope the user happens to have, the broker will grant it. The broker is not a defense against prompt injection. It is a defense against the consequences of prompt injection, by bounding what any single injected instruction can do. The two problems compose; they don't substitute. If your threat model includes prompt injection at all, the broker should be one of two or three layers, not the only one.

Revocation latency is the third. A revoked session can't mint new scoped tokens, but tokens it already minted are valid until they expire. Sixty-second TTLs make this acceptable for almost every threat model I've reviewed. For the ones where it isn't, you need real-time introspection on every tool call, which costs latency on the hot path. Pick which one matters more to you and be explicit about it.

## A demo, if you want to see it run

I built a runnable example of this last week, in the open. It uses Claude as the agent, Keycloak as the IdP, three mock tool services, and a small FastAPI broker that does the token exchange and writes an append-only audit log. There's an HTMX dashboard with a "revoke session" button you can click while the agent is mid-conversation, and watch the next tool call fail clean with the broker's denial reason.

https://github.com/anurag27397/agent-identity-broker

The whole thing is `docker compose up` and a personal Anthropic API key. The `ARCHITECTURE.md` in the repo has the threat model, three sequence diagrams, and an honest list of what would have to change before this is production-ready.

If you're wiring up an AI agent into anything that matters at your company, the question I'd ask first is not what model you're using or which framework. It's: which human is each tool call going to be attributed to, and how would I revoke that human's access if I needed to. If you don't have a clean answer, that's worth starting on before you go further.
