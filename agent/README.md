# agent

Interactive Claude agent that calls the broker-guarded mock tools.

## Run

```bash
# install agent deps in your venv (one-time)
pip install -r agent/requirements.txt

# make sure the rest of the stack is running
docker compose up -d

# set your personal Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...

# go
python agent/main.py
```

Sample prompts:

- `list our customers`
- `what is the balance of account ACC-1004`
- `send ops@example.com a summary of customer C001` (demonstrates the denial path)

## What it shows

For every tool call Claude wants to make, the agent:

1. Asks the broker for a 60-second scoped JWT (`/token/exchange`).
2. If denied, surfaces the broker's reason to Claude as a `tool_result`. Claude
   then explains the denial to the user in natural language.
3. If granted, calls the corresponding mock tool with the scoped token.

The denial path matters: `alice` has the `analyst` role, which can read customer
and finance data but cannot send email. If you ask Claude to email someone,
you'll see the broker reject the exchange (HTTP 403) and Claude tell you why.
