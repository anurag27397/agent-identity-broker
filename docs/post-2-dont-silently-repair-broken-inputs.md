# Don't silently repair structurally broken inputs

*Draft 1. ~380 words. Suitable for LinkedIn long-form, Medium, or a short personal-site post.*

---

My first merged open source PR landed in just-every/code last week. What I shipped wasn't the real lesson. What the maintainer changed before merging was.

The bug: Code (the Codex coding agent) emits some of its prompt instructions as `role: "developer"` messages, following OpenAI's newer convention for o1-class reasoning models. The "OpenAI-compatible" ecosystem (DeepSeek, Moonshot/Kimi, vLLM, llama.cpp servers, certain Groq wrappers) froze on the older role enum and returns 400 on anything outside `{system, user, assistant, tool}`. Every Code request to those providers failed. Not an edge case. Every request.

My fix rewrote any non-standard role to `system` before serialization. Worked. Tests passed. The maintainer (zemaj) merged a follow-up that subtly changed the shape:

```rust
match obj.get("role").and_then(|r| r.as_str()) {
    Some("system" | "user" | "assistant" | "tool") | None => {}
    Some(_) => { /* rewrite unknown string role -> system */ }
}
```

Look at the `None` arm. My version coerced everything non-standard, including a numeric `"role": 42` or a missing role, to `system`. The maintainer split it. An unknown *string* role is a semantic mismatch, a real instruction labeled with a word the provider doesn't recognize, and gets repaired. A wrong-type or absent role is a structural bug in the caller, and gets passed through so the upstream 400 surfaces the actual defect.

The doc comment was explicit: "Missing or non-string roles are left unchanged so malformed payloads fail visibly instead of being silently repaired."

That distinction is the whole post. Repair semantic mismatches. Never mask structural defects. Coercing everything to "safe" defaults feels defensive in the moment and erases the bug your caller needs to find.

The principle generalizes. In an agent identity broker I've been building for AI agents, an unknown `aud` claim returns a 401 with a structured reason that names the audience. Signature verification failures, JSON parse errors, and missing `kid` in the JWKS return the cryptographic failure verbatim, not a generic "auth failed." The audit log is the difference between debuggable and untroubleshootable.

I hadn't articulated the principle until I read zemaj's follow-up commit. Now I have.

PR: https://github.com/just-every/code/pull/417
Broker repo (for the authorization example): https://github.com/anurag27397/agent-identity-broker
