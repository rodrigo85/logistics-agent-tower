"""
Interactive CLI for the Logistics Control Tower (Rich terminal dashboard).
Runs the autonomous multi-agent dispatch workflow, visualizes routes and load allocations,
and prompts the human dispatcher when the HITL gate triggers an interrupt.
"""

import sys
from typing import Any

from langgraph.types import Command
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from logistics_tower.config import settings
from logistics_tower.db.seed import seed_database
from logistics_tower.graph import build_logistics_graph
from logistics_tower.logging_setup import configure_logging
from logistics_tower.memory.short_term import get_session_checkpointer

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")

console = Console(force_terminal=True)


def render_dispatch_dashboard(state_values: dict[str, Any]):
    """Renders formatted operational dispatch tables in terminal."""
    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]🚚 TORRE DE CONTROLE LOGÍSTICO & EXPEDIÇÃO DE CARGAS[/bold cyan]\n"
            f"[bold white]{settings.cd_name}[/bold white]\n"
            f"[dim]{settings.cd_address}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Vehicle Allocation & Capacity Table
    loads = state_values.get("load_allocation", [])
    if loads:
        table_loads = Table(title="📦 Ocupação e Alocação da Frota", border_style="blue")
        table_loads.add_column("Veículo / Placa", style="bold white")
        table_loads.add_column("Modelo / Porte", style="cyan")
        table_loads.add_column("Motorista", style="white")
        table_loads.add_column("Peso Ocupado", justify="right")
        table_loads.add_column("Cubagem Ocupada", justify="right")
        table_loads.add_column("Qtd Pedidos", justify="center")

        for load in loads:
            w_color = (
                "green"
                if load["weight_utilization_pct"] < 85
                else ("yellow" if load["weight_utilization_pct"] <= 90 else "bold red")
            )
            v_color = (
                "green"
                if load["volume_utilization_pct"] < 85
                else ("yellow" if load["volume_utilization_pct"] <= 90 else "bold red")
            )
            ref_tag = " [cyan]❄️ (Ref)[/cyan]" if load.get("has_refrigeration") else ""

            table_loads.add_row(
                f"{load['vehicle_id']}{ref_tag}",
                load.get("vehicle_model", "N/A"),
                load.get("driver_name", "N/A"),
                f"[{w_color}]{load['total_weight_kg']} kg ({load['weight_utilization_pct']}%)[/{w_color}]",
                f"[{v_color}]{load['total_volume_m3']} m³ ({load['volume_utilization_pct']}%)[/{v_color}]",
                str(len(load.get("orders", []))),
            )
        console.print(table_loads)

    # 2. Routes & Stop Sequence Table
    routes = state_values.get("routes", [])
    if routes:
        console.print()
        table_routes = Table(
            title="🗺️ Rotas Otimizadas & Sequência de Entregas (Itajaí / Região)", border_style="magenta"
        )
        table_routes.add_column("Veículo", style="bold white")
        table_routes.add_column("Seq", justify="center")
        table_routes.add_column("Cliente / Destino", style="cyan")
        table_routes.add_column("Previsão (ETA)", justify="center")
        table_routes.add_column("Janela Cliente", justify="center")
        table_routes.add_column("SLA", justify="center")

        for r in routes:
            v_id = r["vehicle_id"]
            for s in r["stops"]:
                sla_badge = "[bold green]✓ No Prazo[/bold green]" if s["on_time"] else "[bold red]✗ Atraso[/bold red]"
                table_routes.add_row(
                    v_id,
                    str(s["sequence"]),
                    f"{s['customer_name']}\n[dim]{s['address']}[/dim]",
                    s["estimated_arrival"],
                    f"{s['window_start']} - {s['window_end']}",
                    sla_badge,
                )
        console.print(table_routes)

    # 3. Risk & Compliance Warnings
    warnings = state_values.get("risk_warnings", [])
    if warnings:
        console.print()
        table_warn = Table(title="⚠️ Alertas de Risco, SLA e Restrições de Doca", border_style="yellow")
        table_warn.add_column("Nível", justify="center")
        table_warn.add_column("Categoria", style="bold")
        table_warn.add_column("Identificador", style="cyan")
        table_warn.add_column("Descrição da Inconsistência", style="white")

        for w in warnings:
            lvl_style = "bold red" if w["level"] == "CRITICAL" else ("yellow" if w["level"] == "WARNING" else "blue")
            table_warn.add_row(
                f"[{lvl_style}]{w['level']}[/{lvl_style}]",
                w["category"],
                w["entity_id"],
                w["description"],
            )
        console.print(table_warn)


def main():
    """CLI execution entrypoint."""
    configure_logging(level="WARNING")
    seed_database()
    console.print("[dim]Iniciando o Squad de Agentes da Torre de Controle Logístico...[/dim]")

    checkpointer = get_session_checkpointer()
    graph = build_logistics_graph(checkpointer=checkpointer)

    thread_id = "cli-session-itj-01"
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "cd_id": settings.default_cd_id,
        "requires_human_approval": False,
        "human_verdict": None,
        "execution_log": [],
    }

    # Run agents until completion or HITL gate interrupt
    graph.invoke(initial_state, config=config)
    curr_state = graph.get_state(config)

    # Render dashboard
    render_dispatch_dashboard(curr_state.values)

    # Check if paused at Human-in-the-Loop gate
    is_paused = bool(curr_state.tasks and any(t.interrupts for t in curr_state.tasks))

    if is_paused:
        console.print()
        console.print(
            Panel.fit(
                f"[bold red]🛑 GATE HUMAN-IN-THE-LOOP ACIONADO[/bold red]\n"
                f"[bold yellow]Motivo:[/bold yellow] {curr_state.values.get('human_approval_reason')}\n"
                f"O sistema de IA pausou o despacho para validação do despachante supervisor.",
                border_style="red",
            )
        )

        choice = (
            console.input(
                "\n[bold white]Decisão do Despachante ([green]A[/green]provar / [red]R[/red]ejeitar): [/bold white]"
            )
            .strip()
            .upper()
        )
        verdict = "APPROVED" if choice in ["A", "APROVAR", "YES", "Y"] else "REJECTED"
        feedback = console.input("[dim]Observação do operador (opcional): [/dim]").strip()

        console.print(f"\n[cyan]Retomando fluxo com decisão: [bold]{verdict}[/bold]...[/cyan]")
        resumed = graph.invoke(
            Command(resume={"verdict": verdict, "feedback": feedback}),
            config=config,
        )

        manifest = resumed.get("dispatch_manifest")
        if manifest:
            console.print(
                Panel.fit(
                    f"[bold green]✅ MANIFESTO ELETRÔNICO DE DESPACHO CONFIRMADO[/bold green]\n"
                    f"ID: [bold white]{manifest['manifest_id']}[/bold white]\n"
                    f"CD: [cyan]{manifest['cd_id']}[/cyan]\n"
                    f"Total Cargas: {manifest['total_orders_dispatched']} pedidos em {manifest['total_vehicles_assigned']} veículos\n"
                    f"Peso Total: {manifest['total_weight_kg']} kg | Cubagem: {manifest['total_volume_m3']} m³\n"
                    f"Status WMS/TMS: [bold green]{manifest['status']}[/bold green]",
                    border_style="green",
                )
            )
        else:
            console.print(
                Panel.fit("[bold red]❌ DESPACHO CANCELADO PELO OPERADOR HUMANO[/bold red]", border_style="red")
            )
    else:
        manifest = curr_state.values.get("dispatch_manifest")
        if manifest:
            console.print(f"\n[bold green]✅ Manifesto {manifest['manifest_id']} gerado sem restrições.[/bold green]")


if __name__ == "__main__":
    main()
