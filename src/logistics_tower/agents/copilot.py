"""
Dispatcher Copilot: a conversational agent that turns operator instructions into
actions on the planning horizon (today and the next days) and re-runs the planning
pipeline for every day it touched.

Examples it handles (Portuguese or English):
- "Não vamos atender o Bistek da Fazenda hoje."                 -> skip_customer_today + replan(today)
- "Passa o Koch de Gravatá para amanhã."                         -> move_customer_orders + replan(today, tomorrow)
- "A Padaria Praia Brava agendou sexta entre 9 e 11."            -> reschedule_customer_window(date="sexta") + replan(friday)
- "O que está previsto para quinta?" / "Por que o MMI-8H12 tem 12 paradas?" -> get_plan_summary / list_orders
- "Lembre que o Koch de Cordeiros só recebe com nota impressa."  -> remember_note

Memory:
- short-term: LangGraph checkpointer keyed by `thread_id` (conversation state);
- long-term: `operator_memory`, `customer_rules` and customer window overrides in SQL, injected in the prompt.

The LLM comes from `llm.provider` (Ollama by default). Mutating tools record their
effects in a per-request action log; the copilot then re-plans every affected day
deterministically, whether or not the model called `replan_dispatch` itself.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import logging
from collections.abc import Callable
from functools import lru_cache
from typing import Annotated, Any, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from logistics_tower.config import settings
from logistics_tower.dates import WEEKDAYS_PT, parse_delivery_date, today
from logistics_tower.db.repository import get_repository
from logistics_tower.llm.provider import get_chat_model
from logistics_tower.mcp import tools as mcp_tools
from logistics_tower.services.dispatch_service import get_dispatch_planner

logger = logging.getLogger(__name__)

MUTATING_TOOLS = {
    "skip_customer_today",
    "restore_customer_today",
    "move_customer_orders",
    "reschedule_customer_window",
}
MAX_TURNS = 8

_actions: contextvars.ContextVar[list[dict[str, Any]]] = contextvars.ContextVar("copilot_actions")


class CopilotState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


# ------------------------------------------------------------------- tools
def _record(name: str, result: Any) -> Any:
    with contextlib.suppress(LookupError):  # tool executed outside run_copilot (e.g. MCP)
        _actions.get().append({"tool": name, "result": result})
    return result


def _signature_proxy(fn: Callable[..., Any], name: str) -> Callable[..., Any]:
    """Return a function with `fn`'s signature that records the call in the action log."""

    @functools.wraps(fn)
    def proxy(*args: Any, **kwargs: Any) -> Any:
        return _record(name, fn(*args, **kwargs))

    proxy.__name__ = name
    return proxy


def get_plan_summary(date: str = "hoje") -> dict[str, Any]:
    """Summarises the latest plan of one delivery date (default today): routes, stops, km, late stops, unallocated orders."""
    return get_dispatch_planner().summary(parse_delivery_date(date))


def replan_dispatch(date: str = "hoje") -> dict[str, Any]:
    """Re-runs the multi-agent planning for one delivery date (default today) and returns the new plan summary."""
    day = parse_delivery_date(date)
    planner = get_dispatch_planner()
    outcome = planner.plan(settings.default_cd_id, plan_date=day)
    summary = planner.summary(day)
    return {
        "thread_id": outcome["thread_id"],
        "plan_date": outcome["plan_date"],
        "date_label": summary["plan_date_label"],
        "status": outcome["status"],
        "approval_reason": outcome.get("approval_reason"),
        "routes": summary["routes"],
        "unallocated_orders": summary["unallocated_orders"],
    }


def build_tools() -> list[StructuredTool]:
    specs: list[tuple[str, Callable[..., Any]]] = [
        ("find_customers", mcp_tools.tool_find_customers),
        ("skip_customer_today", mcp_tools.tool_skip_customer_today),
        ("restore_customer_today", mcp_tools.tool_restore_customer_today),
        ("move_customer_orders", mcp_tools.tool_move_customer_orders),
        ("reschedule_customer_window", mcp_tools.tool_reschedule_customer_window),
        ("list_orders", mcp_tools.tool_list_orders),
        ("remember_note", mcp_tools.tool_remember_note),
        ("get_plan_summary", get_plan_summary),
        ("replan_dispatch", replan_dispatch),
    ]
    return [
        StructuredTool.from_function(func=_signature_proxy(fn, name), name=name, description=fn.__doc__ or "")
        for name, fn in specs
    ]


# ------------------------------------------------------------------ prompt
def build_system_prompt() -> str:
    repo = get_repository()
    planner = get_dispatch_planner()
    memories = repo.get_operator_memories(limit=15)
    memory_lines = "\n".join(f"- [{m['category']}] {m['content']}" for m in memories) or "- (nenhuma)"

    horizon_lines = []
    for row in planner.horizon():
        plan = f"plano {row['plan_status']} com {row['routes']} rotas" if row["plan_status"] else "sem plano calculado"
        horizon_lines.append(
            f"- {row['label']} [{row['date']}]: {row['pending'] + row['dispatched']} pedidos ativos, "
            f"{row['skipped']} excluídos, {plan}"
        )
    now = today()
    return f"""Você é o Copiloto do Despachante da Torre de Controle Logístico do CD Itajaí (distribuição frigorífica).
Hoje é {WEEKDAYS_PT[now.weekday()]}-feira, {now.strftime("%d/%m/%Y")} ({now.isoformat()}).

Horizonte de planejamento (o WMS guarda pedidos para estes dias):
{chr(10).join(horizon_lines)}

Regras de negócio: 5 caminhões frigoríficos, uma rota por caminhão por dia, carregamento às {settings.dock_start_time},
até {settings.max_stops_per_vehicle} paradas por rota, almoço de 1h, jornada máxima de {settings.max_shift_hours:g}h.

Como agir:
1. Para qualquer ação sobre um cliente, passe à ferramenta o nome COMPLETO como o despachante escreveu,
   incluindo loja, bairro e cidade (ex.: 'Angeloni do Centro de Itajaí', 'Giassi de Dom Bosco'); a ferramenta resolve o cliente.
   Se a ferramenta responder AMBIGUOUS ou NOT_FOUND, apresente os candidatos e pergunte qual é o correto; não adivinhe.
2. Datas: passe o argumento `date` exatamente como o despachante falou ("hoje", "amanhã", "quinta", "27/09");
   sem menção a dia, use "hoje". Nunca converta você mesmo dias da semana em datas.
3. "Não vamos atender X hoje/amanhã" -> skip_customer_today(date=...). "Volta a atender X" -> restore_customer_today.
   "Passa X para amanhã/quinta" / "X só pode receber na sexta" -> move_customer_orders(to_date=..., from_date=...).
   "X agendou recebimento entre A e B [na quinta]" -> reschedule_customer_window(date=..., remember=true).
4. Depois de qualquer alteração, chame replan_dispatch(date) uma vez para CADA dia alterado (origem e destino
   quando mover) e resuma o novo plano: rotas, paradas, atrasos e se o gate humano foi acionado.
5. Perguntas sobre um dia -> get_plan_summary(date) ou list_orders(status, date), chamadas UMA vez; responda com contagens
   e no máximo 10 itens listados. Instruções permanentes -> remember_note.
6. Responda em português, de forma objetiva (máximo 6 linhas), citando clientes, datas e horários exatos.
   Nunca invente clientes, pedidos, datas ou horários que as ferramentas não retornaram.

Memória de longo prazo do despachante:
{memory_lines}
"""


# ------------------------------------------------------------------- graph
def build_copilot_graph(
    model: BaseChatModel, checkpointer: Any | None = None, tools: list[StructuredTool] | None = None
):
    tool_list = tools or build_tools()
    bound = model.bind_tools(tool_list)

    def llm_node(state: CopilotState) -> dict[str, Any]:
        messages = state["messages"]
        ai_turns = sum(1 for m in messages if isinstance(m, AIMessage))
        if ai_turns >= MAX_TURNS:
            return {"messages": [AIMessage(content="Limite de passos atingido; resumo do que foi feito acima.")]}
        response = bound.invoke([SystemMessage(content=build_system_prompt()), *messages])
        return {"messages": [response]}

    workflow = StateGraph(CopilotState)
    workflow.add_node("llm", llm_node)
    workflow.add_node("tools", ToolNode(tool_list))
    workflow.add_edge(START, "llm")
    workflow.add_conditional_edges("llm", tools_condition, {"tools": "tools", END: END})
    workflow.add_edge("tools", "llm")
    return workflow.compile(checkpointer=checkpointer or MemorySaver())


def _affected_dates(actions: list[dict[str, Any]]) -> list[str]:
    """Delivery dates touched by successful mutations, in call order (no duplicates)."""
    dates: list[str] = []
    for a in actions:
        if a["tool"] not in MUTATING_TOOLS or not isinstance(a["result"], dict) or a["result"].get("status") != "OK":
            continue
        for key in ("delivery_date", "from_date", "to_date"):
            value = a["result"].get(key)
            if value == "all":
                value = today().isoformat()
            if value and value not in dates:
                dates.append(value)
    return dates


class Copilot:
    """Holds one compiled conversational graph (and its short-term memory) per process."""

    def __init__(self, model: BaseChatModel | None = None) -> None:
        self._model = model
        self._graph: Any = None

    @property
    def graph(self) -> Any:
        if self._graph is None:
            self._graph = build_copilot_graph(self._model or get_chat_model())
        return self._graph

    def chat(self, message: str, thread_id: str) -> dict[str, Any]:
        token = _actions.set([])
        message_token = mcp_tools.operator_message.set(message)
        try:
            result = self.graph.invoke(
                {"messages": [HumanMessage(content=message)]},
                config={"configurable": {"thread_id": thread_id}, "recursion_limit": 2 * MAX_TURNS + 2},
            )
            actions = list(_actions.get())
        finally:
            _actions.reset(token)
            mcp_tools.operator_message.reset(message_token)

        replanned_dates = {
            a["result"].get("plan_date")
            for a in actions
            if a["tool"] == "replan_dispatch" and isinstance(a["result"], dict)
        }
        for day in _affected_dates(actions):
            if day not in replanned_dates:
                actions.append({"tool": "replan_dispatch", "result": replan_dispatch(day), "auto": True})
                replanned_dates.add(day)

        last = result["messages"][-1]
        reply = last.content if isinstance(last.content, str) else str(last.content)
        dispatches = [a["result"] for a in actions if a["tool"] == "replan_dispatch"]
        return {
            "thread_id": thread_id,
            "reply": reply.strip(),
            "actions": actions,
            "replanned": bool(dispatches),
            "dispatch": dispatches[-1] if dispatches else None,
            "dispatches": dispatches,
        }


@lru_cache(maxsize=1)
def get_copilot() -> Copilot:
    return Copilot()
