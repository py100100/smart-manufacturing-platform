"""知识/RAG 数据结构。

- KnowledgeSource：知识来源元数据
- KnowledgeChunk：文档分块
- RetrievalResult：检索结果（source_id、snippet、score）
- CaseMemory：执行案例沉淀（可检索）
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex[:8]}"


SourceType = Literal["project_plan", "memory", "document", "agent_case"]


class KnowledgeSource(BaseModel):
    """知识来源元数据"""

    source_id: str = Field(..., description="来源唯一标识")
    source_name: str = Field(..., description="来源名称，如 project_plan / MEMORY")
    source_type: SourceType = Field(default="document")
    file_path: str = Field(default="", description="文件路径")
    loaded_at: datetime = Field(default_factory=_now)


class KnowledgeChunk(BaseModel):
    """文档分块 — 按 ## 标题切分的最小检索单元"""

    chunk_id: str = Field(default_factory=lambda: _uid("CHK"))
    source_id: str = Field(..., description="所属 KnowledgeSource.source_id")
    source_name: str = Field(default="")
    heading: str = Field(default="", description="所属 ## 标题")
    content: str = Field(..., description="分块文本内容")
    char_count: int = Field(default=0)


class RetrievalResult(BaseModel):
    """单条检索结果"""

    source_id: str = ""
    source_name: str = ""
    source_type: SourceType = "document"
    snippet: str = Field(default="", description="匹配片段（截取前 200 字符）")
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    chunk_id: str = ""
    heading: str = Field(default="", description="所属标题")


class CaseMemory(BaseModel):
    """案例沉淀 — 每次智能体执行后保存的可检索案例"""

    case_id: str = Field(default_factory=lambda: _uid("CASE"))
    request_text: str = Field(..., description="原始请求")
    agent_name: str = Field(default="", description="执行智能体")
    decision: str = Field(default="", description="智能体决策")
    summary: str = Field(default="", description="执行摘要")
    evidence: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    execution_mode: str = Field(default="single")
    stored_at: datetime = Field(default_factory=_now)
