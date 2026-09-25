"""
Pydantic schemas for the Logistics Control Tower REST API.
"""

from typing import Any, Literal

from pydantic import BaseModel, Field

from logistics_tower.config import settings

DispatchStatus = Literal["COMPLETED", "AWAITING_HUMAN_APPROVAL", "REJECTED"]
HumanVerdict = Literal["APPROVED", "REJECTED", "OVERRIDE"]


class DispatchRequest(BaseModel):
    cd_id: str = Field(default=settings.default_cd_id, description="Distribution Center identifier")
    auto_approve: bool = Field(default=False, description="Bypass the Human-in-the-Loop interrupt")


class ResumeHITLRequest(BaseModel):
    thread_id: str = Field(description="Execution thread currently paused at the HITL gate")
    verdict: HumanVerdict = Field(default="APPROVED", description="Human decision")
    feedback: str = Field(default="", description="Operator notes or reasoning")


class DispatchResponse(BaseModel):
    thread_id: str
    status: DispatchStatus
    requires_approval: bool
    approval_reason: str | None = None
    risk_warnings: list[dict[str, Any]] = Field(default_factory=list)
    manifest: dict[str, Any] | None = None
    execution_log: list[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    version: str
    env: str


class GenerateOrdersResponse(BaseModel):
    status: Literal["ok"]
    message: str
    count: int
    orders: list[dict[str, Any]]


class TrafficStatusResponse(BaseModel):
    provider: str
    configured: bool
    live_traffic_enabled: bool
    message: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000, description="Operator instruction or question")
    thread_id: str | None = Field(default=None, description="Conversation thread (short-term memory)")


class ChatResponse(BaseModel):
    thread_id: str
    reply: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    replanned: bool = False
    dispatch: dict[str, Any] | None = None


class CopilotStatusResponse(BaseModel):
    provider: str
    model: str | None = None
    available: bool
    detail: str = ""
    tools: list[str] = Field(default_factory=list)


class AgentsResponse(BaseModel):
    version: str
    env: str
    planning_agents: list[dict[str, Any]]
    mcp_tools: list[str]
    copilot_tools: list[str]
    latest_plan: dict[str, Any]
