"""
Dispatcher Copilot: a conversational agent that turns operator instructions into
actions on today's plan and re-runs the planning pipeline.

Examples it handles (Portuguese or English):
- "Não vamos atender o Bistek da Fazenda hoje."          -> skip_customer_today + replan
- "A Padaria Praia Brava agendou recebimento entre 9 e 11." -> reschedule_customer_window + replan
- "Por que o MMI-8H12 tem 12 paradas?"                    -> get_plan_summary
- "Lembre que o Koch de Cordeiros só recebe com nota impressa." -> remember_note

Memory:
- short-term: LangGraph checkpointer keyed by `thread_id` (conversation state);
- long-term: `operator_memory` and `customer_rules` tables, injected in the system prompt.

The LLM comes from `llm.provider` (Ollama by default). Mutating tools record their
effects in a per-request action log; when something changed and the model did not
call `replan_dispatch` itself, the copilot re-plans deterministically at the end.
"""

from __future__ import annotations

import contextlib
import contextvars
import logging
from collections.abc import Callable
from datetime import datetime
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
from logistics_tower.db.repository import get_repository
from logistics_tower.llm.provider import get_chat_model
from logistics_tower.mcp import tools as mcp_tools
from logistics_tower.services.dispatch_service import get_dispatch_planner

logger = logging.getLogger(__name__)

MUTATING_TOOLS = {"skip_customer_today", "restore_customer_today", "reschedule_customer_window"}
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
    import functools

    @functools.wraps(fn)
    def proxy(*args: Any, **kwargs: Any) -> Any:
        return _record(name, fn(*args, **kwargs))

    proxy.__name__ = name
    return proxy


def get_plan_summary() -> dict[str, Any]:
    """Summarises the latest dispatch plan: routes per vehicle, stops, km, late stops, unallocated orders and warnings."""
    return get_dispatch_planner().summary()


def replan_dispatch() -> dict[str, Any]:
    """Re-runs the multi-agent planning for today's pending orders and returns the new plan summary and status."""
    outcome = get_dispatch_planner().plan(settings.default_cd_id)
    summary = get_dispatch_planner().summary()
    result = {
        "thread_id": outcome["thread_id"],
        "status": outcome["status"],
        "approval_reason": outcome.get("approval_reason"),
        "routes": summary["routes"],
        "unallocated_orders": summary["unallocated_orders"],
    }
    return result


def build_tools() -> list[StructuredTool]:
    specs: list[tuple[str, Callable[..., Any], str]] = [
        ("find_customers", mcp_tools.tool_find_customers, mcp_tools.tool_find_customers.__doc__ or ""),
        ("skip_customer_today", mcp_tools.tool_skip_customer_today, mcp_tools.tool_skip_customer_today.__doc__ or ""),
        (
            "restore_customer_today",
            mcp_tools.tool_restore_customer_today,
            mcp_tools.tool_restore_customer_today.__doc__ or "",
        ),
        (
            "reschedule_customer_window",
            mcp_tools.tool_reschedule_customer_window,
            mcp_tools.tool_reschedule_customer_window.__doc__ or "",
        ),
        ("list_orders", mcp_tools.tool_list_orders, mcp_tools.tool_list_orders.__doc__ or ""),
        ("remember_note", mcp_tools.tool_remember_note, mcp_tools.tool_remember_note.__doc__ or ""),
        ("get_plan_summary", get_plan_summary, get_plan_summary.__doc__ or ""),
        ("replan_dispatch", replan_dispatch, replan_dispatch.__doc__ or ""),
    ]
    return [
        StructuredTool.from_function(func=_signature_proxy(fn, name), name=name, description=desc)
        for name, fn, desc in specs
    ]


# ------------------------------------------------------------------ prompt
def build_system_prompt() -> str:
    repo = get_repository()
    pending = repo.get_pending_orders(settings.default_cd_id)
    skipped = repo.get_orders_by_status("SKIPPED", settings.default_cd_id)
    memories = repo.get_operator_memories(limit=15)
    plan = get_dispatch_planner().summary()

    memory_lines = "\n".join(f"- [{m['category']}] {m['content']}" for m in memories) or "- (nenhuma)"
    plan_line = (
        f"Último plano: {plan['status']} com {len(plan['routes'])} rotas"
        if plan["status"]
        else "Ainda não há plano calculado hoje."
    )
    return f"""Você é o Copiloto do Despachante da Torre de Controle Logístico do CD Itajaí (distribuição frigorífica).
Hoje é {datetime.now().strftime("%d/%m/%Y")}. Pedidos pendentes: {len(pending)}. Pedidos excluídos de hoje: {len(skipped)}. {plan_line}

Regras de negócio: 5 caminhões frigoríficos, uma rota por caminhão por dia, carregamento às {settings.dock_start_time},
até {settings.max_stops_per_vehicle} paradas por rota, almoço de 1h, jornada máxima de {settings.max_shift_hours:g}h.

Como agir:
1. Para qualquer ação sobre um cliente, passe à ferramenta o nome COMPLETO como o despachante escreveu,
   incluindo loja, bairro e cidade (ex.: 'Angeloni do Centro de Itajaí', 'Giassi de Dom Bosco'); a ferramenta resolve o cliente.
   Se a ferramenta responder AMBIGUOUS ou NOT_FOUND, apresente os candidatos e pergunte qual é o correto; não adivinhe.
2. "Não vamos atender X hoje" / "tira X de hoje" -> skip_customer_today. "Volta a atender X" -> restore_customer_today.
3. "X agendou recebimento entre A e B" / "X só recebe das A às B" -> reschedule_customer_window (remember=true).
4. Depois de qualquer alteração, chame replan_dispatch uma única vez e resuma o novo plano
   (rotas, paradas, atrasos e se o gate humano foi acionado).
5. Perguntas sobre o plano -> get_plan_summary. Instruções permanentes do despachante -> remember_note.
6. Responda em português, de forma objetiva (máximo 6 linhas), citando clientes e horários exatos.
   Nunca invente clientes, pedidos ou horários que as ferramentas não retornaram.

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

        mutated = any(a["tool"] in MUTATING_TOOLS and a["result"].get("status") == "OK" for a in actions)
        replanned = any(a["tool"] == "replan_dispatch" for a in actions)
        if mutated and not replanned:
            actions.append({"tool": "replan_dispatch", "result": replan_dispatch(), "auto": True})
            replanned = True

        last = result["messages"][-1]
        reply = last.content if isinstance(last.content, str) else str(last.content)
        dispatch = next((a["result"] for a in reversed(actions) if a["tool"] == "replan_dispatch"), None)
        return {
            "thread_id": thread_id,
            "reply": reply.strip(),
            "actions": actions,
            "replanned": replanned,
            "dispatch": dispatch,
        }


@lru_cache(maxsize=1)
def get_copilot() -> Copilot:
    return Copilot()
