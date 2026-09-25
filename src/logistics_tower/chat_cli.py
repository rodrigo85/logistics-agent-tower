"""
Terminal chat with the Dispatcher Copilot.

    logistics-tower-chat            # interactive session
    logistics-tower-chat "Não vamos atender o Bistek da Fazenda hoje"
"""

import sys
import uuid

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from logistics_tower.agents.copilot import get_copilot
from logistics_tower.db.seed import seed_database
from logistics_tower.llm.provider import LLMNotConfiguredError, llm_status
from logistics_tower.logging_setup import configure_logging

console = Console(force_terminal=True)


def _print_result(result: dict) -> None:
    console.print(Panel(Markdown(result["reply"]), title="Copiloto", border_style="cyan"))
    for action in result["actions"]:
        tag = "auto" if action.get("auto") else "tool"
        status = action["result"].get("status") if isinstance(action["result"], dict) else ""
        console.print(f"[dim]  [{tag}] {action['tool']} {status or ''}[/dim]")
    if result.get("dispatch"):
        d = result["dispatch"]
        console.print(f"[bold]  Plano {d['thread_id']}: {d['status']}[/bold] ({len(d['routes'])} rotas)")


def main() -> None:
    configure_logging(level="WARNING")
    seed_database()
    status = llm_status()
    if not status["available"]:
        console.print(f"[red]LLM indisponível ({status['provider']}): {status['detail']}[/red]")
        sys.exit(1)

    copilot = get_copilot()
    thread_id = f"cli-{uuid.uuid4().hex[:6]}"
    console.print(f"[dim]Copiloto do Despachante · {status['provider']}/{status['model']} · thread {thread_id}[/dim]")

    if len(sys.argv) > 1:
        try:
            _print_result(copilot.chat(" ".join(sys.argv[1:]), thread_id))
        except LLMNotConfiguredError as exc:
            console.print(f"[red]{exc}[/red]")
            sys.exit(1)
        return

    console.print(
        "[dim]Digite a instrução (ex.: 'Não vamos atender o Koch de Cordeiros hoje'). 'sair' para encerrar.[/dim]"
    )
    while True:
        try:
            text = console.input("[bold cyan]despachante>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not text or text.lower() in {"sair", "exit", "quit"}:
            break
        try:
            _print_result(copilot.chat(text, thread_id))
        except LLMNotConfiguredError as exc:
            console.print(f"[red]{exc}[/red]")
            break


if __name__ == "__main__":
    main()
