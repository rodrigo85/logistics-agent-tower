"""
Tests for the Dispatcher Copilot.

A scripted chat model stands in for the LLM: it maps operator sentences to tool
calls exactly like a tool-calling model would, so the tests exercise the real
LangGraph loop, the real tools and the real database effects without a provider.
Provider-backed behaviour is covered by `evals/run_evals.py`.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from logistics_tower.agents.copilot import Copilot
from logistics_tower.api.main import app
from logistics_tower.config import settings
from logistics_tower.db.repository import get_repository
from logistics_tower.mcp.tools import normalize_clock, tool_skip_customer_today
from logistics_tower.services.dispatch_service import get_dispatch_planner


class ScriptedChatModel(BaseChatModel):
    """Deterministic stand-in for a tool-calling LLM."""

    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> BaseChatModel:
        return self

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        self.calls += 1
        last = messages[-1]
        if isinstance(last, ToolMessage):
            tool_results = [m for m in messages if isinstance(m, ToolMessage)]
            return self._final(f"Feito. Resultado: {tool_results[-1].content[:160]}")
        assert isinstance(last, HumanMessage)
        text = str(last.content)
        low = text.lower()

        m = re.search(
            r"^(amanhã|amanha|hoje|quinta|sexta) não vamos atender (?:o |a )?(.+?)\.?$", text, flags=re.IGNORECASE
        )
        if m:
            return self._tool(
                "skip_customer_today",
                {"customer": m.group(2).strip(), "reason": "Solicitado pelo despachante", "date": m.group(1)},
            )
        m = re.search(r"não vamos atender (?:o |a )?(.+?) hoje", low)
        if m:
            customer = text[m.start(1) : m.end(1)]
            return self._tool("skip_customer_today", {"customer": customer, "reason": "Solicitado pelo despachante"})
        m = re.search(r"passa (?:o |a )?(.+?) para (\S+)", text, flags=re.IGNORECASE)
        if m:
            return self._tool("move_customer_orders", {"customer": m.group(1).strip(), "to_date": m.group(2)})
        m = re.search(r"(.+?) agendou recebimento entre (\S+) e (\S+)", text, flags=re.IGNORECASE)
        if m:
            return self._tool(
                "reschedule_customer_window",
                {
                    "customer": m.group(1).strip(),
                    "window_start": m.group(2),
                    "window_end": m.group(3),
                    "remember": True,
                },
            )
        m = re.search(r"volt(?:a|e) a atender (?:o |a )?(.+?)(?: hoje)?$", text, flags=re.IGNORECASE)
        if m:
            return self._tool("restore_customer_today", {"customer": m.group(1).strip()})
        if "lembre" in low:
            return self._tool("remember_note", {"note": text})
        if any(k in low for k in ("plano", "paradas", "por que", "resumo")):
            return self._tool("get_plan_summary", {})
        return self._final("Não entendi a instrução.")

    @staticmethod
    def _tool(name: str, args: dict[str, Any]) -> ChatResult:
        msg = AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call-{name}"}])
        return ChatResult(generations=[ChatGeneration(message=msg)])

    @staticmethod
    def _final(text: str) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


@pytest.fixture
def copilot() -> Copilot:
    return Copilot(model=ScriptedChatModel())


def _customer_with_pending_order(exclude: set[str] = frozenset()) -> str:
    orders = get_repository().get_pending_orders(settings.default_cd_id)
    return next(o["customer_name"] for o in orders if o["customer_name"] not in exclude)


# ------------------------------------------------------------------ tools
def test_normalize_clock_variants():
    assert normalize_clock("8") == "08:00"
    assert normalize_clock("8h") == "08:00"
    assert normalize_clock("8:30") == "08:30"
    assert normalize_clock("08h30") == "08:30"
    assert normalize_clock("14 horas") == "14:00"
    with pytest.raises(ValueError):
        normalize_clock("25:00")


def test_find_customers_exact_and_fuzzy():
    repo = get_repository()
    exact = repo.find_customers("Supermercado Bistek - Fazenda")
    assert exact[0]["customer_name"] == "Supermercado Bistek - Fazenda"
    assert exact[0]["match_score"] == 1.0
    fuzzy = repo.find_customers("bistek fazenda")
    assert fuzzy[0]["customer_name"] == "Supermercado Bistek - Fazenda"
    assert repo.find_customers("cliente inexistente xyz") == []


def test_skip_tool_is_ambiguous_for_chain_names_and_does_not_mutate():
    result = tool_skip_customer_today("Koch")
    assert result["status"] == "AMBIGUOUS"
    assert len(result["candidates"]) > 1
    assert not get_repository().get_orders_by_status("SKIPPED")


# ---------------------------------------------------------------- copilot
def test_copilot_skips_customer_and_replans(copilot):
    customer = _customer_with_pending_order()
    before = len(get_repository().get_pending_orders(settings.default_cd_id))

    result = copilot.chat(f"Não vamos atender {customer} hoje", thread_id="t-skip")

    tools_called = [a["tool"] for a in result["actions"]]
    assert "skip_customer_today" in tools_called
    assert result["replanned"] is True and result["dispatch"] is not None
    assert tools_called[-1] == "replan_dispatch"

    skipped = get_repository().get_orders_by_status("SKIPPED")
    assert {o["customer_name"] for o in skipped} == {customer}
    assert len(get_repository().get_pending_orders(settings.default_cd_id)) == before - len(skipped)

    planned_customers = {c for r in get_dispatch_planner().summary()["routes"] for c in r["customers"]}
    assert customer not in planned_customers
    assert result["reply"]


def test_copilot_reschedules_window_and_remembers_it(copilot):
    customer = _customer_with_pending_order()

    result = copilot.chat(f"{customer} agendou recebimento entre 9 e 11", thread_id="t-window")

    action = next(a for a in result["actions"] if a["tool"] == "reschedule_customer_window")
    assert action["result"]["status"] == "OK"
    assert action["result"]["window"] == "09:00 - 11:00"
    assert result["replanned"] is True

    repo = get_repository()
    order = next(o for o in repo.get_pending_orders(settings.default_cd_id) if o["customer_name"] == customer)
    assert (order["window_start"], order["window_end"]) == ("09:00", "11:00")
    assert repo.find_customers(customer)[0]["window_override"] == "09:00 - 11:00"
    assert any("09:00" in r["content"] for r in repo.get_all_customer_rules() if r["customer_name"] == customer)
    assert any(m["category"] == "WINDOW" for m in repo.get_operator_memories())

    stop = next(s for r in get_dispatch_planner().latest.routes for s in r["stops"] if s["customer_name"] == customer)
    assert (stop["window_start"], stop["window_end"]) == ("09:00", "11:00")


def test_copilot_restores_skipped_customer(copilot):
    customer = _customer_with_pending_order()
    copilot.chat(f"Não vamos atender {customer} hoje", thread_id="t-restore")
    assert get_repository().get_orders_by_status("SKIPPED")

    result = copilot.chat(f"Volta a atender {customer} hoje", thread_id="t-restore")

    assert next(a for a in result["actions"] if a["tool"] == "restore_customer_today")["result"]["status"] == "OK"
    assert not get_repository().get_orders_by_status("SKIPPED")
    assert result["replanned"] is True


def test_copilot_asks_when_customer_is_ambiguous(copilot):
    result = copilot.chat("Não vamos atender Koch hoje", thread_id="t-amb")
    action = next(a for a in result["actions"] if a["tool"] == "skip_customer_today")
    assert action["result"]["status"] == "AMBIGUOUS"
    assert result["replanned"] is False
    assert not get_repository().get_orders_by_status("SKIPPED")


def test_copilot_keeps_conversation_state_per_thread(copilot):
    copilot.chat("Lembre que o motorista do Truck sai sempre por último", thread_id="t-mem")
    assert any(m["category"] == "NOTE" for m in get_repository().get_operator_memories())
    snapshot = copilot.graph.get_state({"configurable": {"thread_id": "t-mem"}})
    assert len(snapshot.values["messages"]) >= 3  # human, tool call, tool result, final answer


# -------------------------------------------------------------------- API
client = TestClient(app)


def test_api_copilot_status_and_agents_registry():
    status = client.get("/copilot/status").json()
    assert status["provider"] in {"ollama", "gemini", "openai"}
    assert "skip_customer_today" in status["tools"]

    agents = client.get("/agents").json()
    names = {a["name"] for a in agents["planning_agents"]}
    assert {"supervisor", "fleet_agent", "routing_agent", "risk_agent", "hitl_gate", "copilot"} <= names
    assert "reschedule_customer_window" in agents["mcp_tools"]


def test_api_chat_applies_instruction(monkeypatch):
    import logistics_tower.api.routers.copilot as copilot_router

    monkeypatch.setattr(copilot_router, "get_copilot", lambda: Copilot(model=ScriptedChatModel()))
    customer = _customer_with_pending_order()

    res = client.post("/copilot/chat", json={"message": f"Não vamos atender {customer} hoje"})
    assert res.status_code == 200
    body = res.json()
    assert body["thread_id"].startswith("chat-")
    assert body["replanned"] is True
    assert body["dispatch"]["status"] in {"COMPLETED", "AWAITING_HUMAN_APPROVAL"}

    data = client.get("/api/dashboard-data").json()
    assert {o["customer_name"] for o in data["skipped_orders"]} == {customer}
    assert data["plan_thread_id"] == body["dispatch"]["thread_id"]


def test_api_chat_reports_missing_llm(monkeypatch):
    from logistics_tower.llm.provider import LLMNotConfiguredError

    class Broken:
        def chat(self, *_):
            raise LLMNotConfiguredError("sem provedor")

    import logistics_tower.api.routers.copilot as copilot_router

    monkeypatch.setattr(copilot_router, "get_copilot", lambda: Broken())
    res = client.post("/copilot/chat", json={"message": "oi"})
    assert res.status_code == 503


def test_tool_uses_operator_sentence_to_disambiguate_chain_stores():
    """'Angeloni' alone is ambiguous (two stores); the full sentence names the Itajaí store."""
    from logistics_tower.mcp import tools as mcp_tools

    token = mcp_tools.operator_message.set("Tira o Angeloni do Centro de Itajaí da rota de hoje")
    try:
        match, candidates = mcp_tools._resolve_customer("Angeloni")
    finally:
        mcp_tools.operator_message.reset(token)
    assert len(candidates) == 2
    assert match is not None and match["customer_name"] == "Angeloni Supermercados - Centro"

    match, _ = mcp_tools._resolve_customer("Angeloni")  # no sentence context -> still ambiguous
    assert match is None


def test_skip_after_approved_plan_still_removes_customer(copilot):
    """Operators change plans after approval too: skipping must cover DISPATCHED orders and the replan drops them."""
    get_dispatch_planner().plan(settings.default_cd_id, auto_approve=True)
    customer = get_dispatch_planner().latest.routes[0]["stops"][0]["customer_name"]

    result = copilot.chat(f"Não vamos atender {customer} hoje", thread_id="t-skip-after-approval")

    action = next(a for a in result["actions"] if a["tool"] == "skip_customer_today")
    assert action["result"]["status"] == "OK"
    planned = {c for r in get_dispatch_planner().summary()["routes"] for c in r["customers"]}
    assert customer not in planned


def _customer_with_order_on(offset: int) -> str:
    from datetime import timedelta

    from logistics_tower.dates import today

    day = today() + timedelta(days=offset)
    return get_repository().get_pending_orders(settings.default_cd_id, delivery_date=day)[0]["customer_name"]


def test_copilot_moves_customer_to_tomorrow_and_replans_both_days(copilot):
    from datetime import timedelta

    from logistics_tower.dates import today

    customer = _customer_with_pending_order()
    tomorrow = today() + timedelta(days=1)

    result = copilot.chat(f"Passa {customer} para amanhã", thread_id="t-move")

    action = next(a for a in result["actions"] if a["tool"] == "move_customer_orders")
    assert action["result"]["status"] == "OK"
    assert action["result"]["to_date"] == tomorrow.isoformat()
    replanned = {d["plan_date"] for d in result["dispatches"]}
    assert replanned == {today().isoformat(), tomorrow.isoformat()}

    repo = get_repository()
    assert customer not in {o["customer_name"] for o in repo.get_pending_orders(settings.default_cd_id)}
    assert customer in {o["customer_name"] for o in repo.get_pending_orders(settings.default_cd_id, tomorrow)}
    planned_tomorrow = {c for r in get_dispatch_planner().summary(tomorrow)["routes"] for c in r["customers"]}
    assert customer in planned_tomorrow


def test_copilot_skips_customer_tomorrow_only(copilot):
    from datetime import timedelta

    from logistics_tower.dates import today

    tomorrow = today() + timedelta(days=1)
    customer = _customer_with_order_on(1)
    today_before = len(get_repository().get_pending_orders(settings.default_cd_id))

    result = copilot.chat(f"Amanhã não vamos atender {customer}", thread_id="t-skip-tomorrow")

    action = next(a for a in result["actions"] if a["tool"] == "skip_customer_today")
    assert action["result"]["status"] == "OK"
    assert action["result"]["delivery_date"] == tomorrow.isoformat()
    assert [d["plan_date"] for d in result["dispatches"]] == [tomorrow.isoformat()]
    repo = get_repository()
    assert {o["customer_name"] for o in repo.get_orders_by_status("SKIPPED", delivery_date=tomorrow)} == {customer}
    assert len(repo.get_pending_orders(settings.default_cd_id)) == today_before  # today untouched
