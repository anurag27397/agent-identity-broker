"""Interactive Claude agent that calls broker-guarded tools.

Usage:
  export ANTHROPIC_API_KEY=sk-ant-...
  python agent/main.py

The agent logs in as alice (the demo user) and runs a chat loop. Every
tool call goes through the broker for a 60-second scoped JWT first; if
the broker denies it, the agent surfaces that to Claude and Claude can
explain the denial to the user.

Run the docker-compose stack before this:
  docker compose up -d
"""

import json
import os
import sys
from typing import Any

from anthropic import Anthropic
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from broker_client import BrokerClient
from tools import TOOL_DEFINITIONS, TOOL_EXECUTORS


MODEL = os.getenv("AGENT_MODEL", "claude-haiku-4-5-20251001")
BROKER_URL = os.getenv("BROKER_URL", "http://localhost:8001")

SYSTEM_PROMPT = (
    "You are a financial analyst assistant for alice. Use the available tools "
    "to answer her questions about customers and accounts. When a tool call "
    "fails because of a permission denial, explain to alice exactly which "
    "scope you were denied and why she might need a higher-privileged session "
    "to do that. Keep replies short and concrete."
)


console = Console()


def _render_tool_call(name: str, params: dict) -> None:
    console.print(
        Panel(
            Syntax(json.dumps(params, indent=2), "json", theme="monokai"),
            title=f"[bold cyan]tool_use[/bold cyan] {name}",
            border_style="cyan",
            expand=False,
        )
    )


def _render_tool_result(name: str, result: dict) -> None:
    border = "red" if result.get("error") else "green"
    title = f"[bold {border}]tool_result[/bold {border}] {name}"
    if "permission_denied" in result:
        title = f"[bold red]tool_result (DENIED)[/bold red] {name}"
    text = json.dumps(result, indent=2, default=str)
    console.print(
        Panel(Syntax(text, "json", theme="monokai"), title=title, border_style=border, expand=False)
    )


def _login(broker: BrokerClient) -> None:
    console.print("[dim]Logging in as alice ...[/dim]")
    info = broker.login("alice", "alice")
    console.print(
        f"[green]logged in[/green] as [bold]{info.preferred_username}[/bold] "
        f"(roles: {', '.join(info.roles) or 'none'})"
    )


def _process_tools(broker: BrokerClient, content_blocks: list[Any]) -> list[dict]:
    results: list[dict] = []
    for block in content_blocks:
        if block.type != "tool_use":
            continue
        _render_tool_call(block.name, block.input or {})
        executor = TOOL_EXECUTORS.get(block.name)
        if not executor:
            result: dict = {"error": f"unknown tool {block.name!r}"}
        else:
            result = executor(broker, block.input or {})
        _render_tool_result(block.name, result)
        results.append(
            {
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result),
                "is_error": bool(result.get("error")),
            }
        )
    return results


def _emit_text(content_blocks: list[Any]) -> None:
    for block in content_blocks:
        if block.type == "text" and block.text.strip():
            console.print(Panel(block.text.strip(), title="[bold]assistant[/bold]", border_style="white", expand=False))


def run_turn(client: Anthropic, broker: BrokerClient, messages: list[dict]) -> None:
    """Drive the tool-use loop for one user turn."""
    while True:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            _emit_text(resp.content)
            return

        tool_results = _process_tools(broker, resp.content)
        messages.append({"role": "user", "content": tool_results})


def main() -> int:
    if not os.getenv("ANTHROPIC_API_KEY"):
        console.print("[red]ANTHROPIC_API_KEY is not set[/red]")
        return 1

    broker = BrokerClient(BROKER_URL)
    try:
        _login(broker)
    except Exception as e:
        console.print(f"[red]login failed: {e}[/red]")
        console.print("[dim]is the stack running? docker compose up -d[/dim]")
        return 2

    client = Anthropic()
    messages: list[dict] = []

    console.print("\n[dim]Ask things like 'list customers', 'how much is in account ACC-1004',[/dim]")
    console.print("[dim]or 'email ops@example.com a summary'. Ctrl-D / Ctrl-C to exit.[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold blue]you[/bold blue] > ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return 0
        if not user_input.strip():
            continue
        if user_input.strip().lower() in {"quit", "exit", ":q"}:
            return 0

        messages.append({"role": "user", "content": user_input.strip()})
        try:
            run_turn(client, broker, messages)
        except Exception as e:
            console.print(f"[red]turn failed: {e}[/red]")


if __name__ == "__main__":
    sys.exit(main())
