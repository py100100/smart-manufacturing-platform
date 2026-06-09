from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.schemas.agent import NodeFeedback


@dataclass(slots=True)
class AgentResult:
    summary: str
    decision: str
    evidence: list[str]
    next_actions: list[str]
    node_feedback: list = field(default_factory=list)


class BaseAgent(ABC):
    name: str
    display_name: str
    scenario_hint: str

    @abstractmethod
    def plan(self, request_text: str, context: dict[str, str]) -> AgentResult:
        raise NotImplementedError

    def build_node_feedback(self, request_text: str, result: AgentResult) -> list[NodeFeedback]:
        now = datetime.now(timezone.utc)
        nodes = [
            NodeFeedback(
                node_id=f"{self.name}-intent",
                node_name="意图识别",
                status="completed",
                detail=f"已识别为{self.display_name}场景，请求内容：{request_text[:60]}",
                started_at=now,
                completed_at=now,
            ),
            NodeFeedback(
                node_id=f"{self.name}-analysis",
                node_name="规则分析",
                status="completed",
                detail=result.summary,
                started_at=now,
                completed_at=now,
            ),
            NodeFeedback(
                node_id=f"{self.name}-decision",
                node_name="决策输出",
                status="completed",
                detail=result.decision,
                started_at=now,
                completed_at=now,
            ),
        ]
        result.node_feedback = nodes
        return nodes
