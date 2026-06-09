"""知识/RAG 服务。

- 离线文档分块（按 ## 标题切分）
- LangChain + Chroma 向量检索优先
- 关键词 + 轻量 TF-IDF 相似度检索兜底
- RetrievalResult 带 source_id / source_name / snippet / score
- 案例沉淀与检索
"""

from __future__ import annotations

import re
from collections import Counter
from hashlib import sha256
from math import log
from pathlib import Path
from uuid import uuid4

from app.core.config import BASE_DIR
from app.schemas.knowledge_rag import (
    CaseMemory,
    KnowledgeChunk,
    KnowledgeSource,
    RetrievalResult,
    SourceType,
)

try:
    from langchain_chroma import Chroma
    from langchain_core.documents import Document
    from langchain_core.embeddings import Embeddings
except ImportError:  # pragma: no cover - optional RAG stack fallback
    Chroma = None
    Document = None
    Embeddings = object


class LocalHashEmbeddings(Embeddings):
    """离线轻量 embedding，用于 Chroma 演示环境。

    不依赖外部模型服务，保证项目在无网络、无 API Key 时仍可运行。
    后续可替换为 Qwen / bge / text2vec 等真实 embedding 模型。
    """

    def __init__(self, dimensions: int = 128) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = KnowledgeService._tokenize(text)
        if not tokens:
            tokens = [text[:32] or "empty"]

        for token in tokens:
            digest = sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = sum(v * v for v in vector) ** 0.5
        if norm == 0.0:
            return vector
        return [v / norm for v in vector]


class KnowledgeService:
    """知识检索服务。

    优先使用 LangChain + Chroma 做向量检索；当依赖未安装或初始化失败时，
    自动回退到内存级 TF-IDF，保证现有智能体流程不受影响。
    """

    def __init__(self) -> None:
        self.sources: dict[str, KnowledgeSource] = {}
        self.chunks: list[KnowledgeChunk] = []
        self.cases: list[CaseMemory] = []
        # TF-IDF 词表
        self._term_index: dict[str, dict[str, int]] = {}  # chunk_id → {term: tf}
        self._idf: dict[str, float] = {}
        self._vector_store = None
        self._vector_enabled = False

        # 初始化加载
        self._load_sources()
        self._build_index()
        self._build_vector_store()

    # ── 文档加载与分块 ────────────────────────────────────

    def _load_sources(self) -> None:
        """加载项目中的 .md 文件并分块。"""
        doc_paths: list[tuple[str, str, SourceType, Path]] = [
            (
                "project_plan",
                "项目方案",
                "project_plan",
                BASE_DIR / "基于Agentic RAG与多智能体协作智能制造服务平台.md",
            ),
            (
                "project_plan_v2",
                "智能制造多智能体协作方案",
                "project_plan",
                BASE_DIR / "基于智能制造多智能体协作服务平台.md",
            ),
            ("memory", "跨会话记忆", "memory", BASE_DIR / "MEMORY.md"),
            ("claude", "项目规则", "document", BASE_DIR / "CLAUDE.md"),
            ("agents", "智能体指南", "document", BASE_DIR / "AGENTS.md"),
        ]

        for source_id, source_name, stype, path in doc_paths:
            if not path.exists():
                continue
            self.sources[source_id] = KnowledgeSource(
                source_id=source_id,
                source_name=source_name,
                source_type=stype,
                file_path=str(path),
            )
            text = path.read_text(encoding="utf-8", errors="ignore")
            self._chunk_document(source_id, source_name, text)

    def _chunk_document(
        self, source_id: str, source_name: str, text: str
    ) -> None:
        """按 ## 标题将文档切分为 KnowledgeChunk。"""
        # 按 ## 分割
        sections = re.split(r"\n(?=## )", text)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            # 提取第一个 ## 标题
            heading_match = re.match(r"^##\s+(.+)", section)
            heading = heading_match.group(1).strip() if heading_match else "概述"
            content = section
            self.chunks.append(
                KnowledgeChunk(
                    source_id=source_id,
                    source_name=source_name,
                    heading=heading,
                    content=content,
                    char_count=len(content),
                )
            )

    # ── 索引构建 ──────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """中文+英文分词（轻量：按标点/空白切分，保留 ≥2 字符的词）。"""
        tokens = re.findall(r"[一-鿿]{1,4}|[a-zA-Z]{2,}|[0-9]+", text.lower())
        return [t for t in tokens if len(t) >= 2]

    def _build_index(self) -> None:
        """构建 TF-IDF 词表。"""
        self._term_index.clear()
        df: Counter[str] = Counter()  # document frequency

        for ch in self.chunks:
            tokens = self._tokenize(ch.content)
            tf = Counter(tokens)
            self._term_index[ch.chunk_id] = dict(tf)
            for term in set(tokens):
                df[term] += 1

        total = len(self.chunks)
        self._idf = {
            term: log((total + 1) / (freq + 1)) + 1.0
            for term, freq in df.items()
        }

    def _build_vector_store(self) -> None:
        """构建 LangChain + Chroma 向量索引。

        使用内存 Chroma，不写入本地文件；如果 LangChain/Chroma 不可用，
        保持 `_vector_enabled=False` 并由 TF-IDF 兜底。
        """
        if Chroma is None or Document is None or not self.chunks:
            self._vector_enabled = False
            return

        documents = [
            Document(
                page_content=ch.content,
                metadata={
                    "source_id": ch.source_id,
                    "source_name": ch.source_name,
                    "chunk_id": ch.chunk_id,
                    "heading": ch.heading,
                },
            )
            for ch in self.chunks
        ]

        try:
            self._vector_store = Chroma.from_documents(
                documents=documents,
                embedding=LocalHashEmbeddings(),
                collection_name=f"smart_manufacturing_knowledge_{uuid4().hex[:8]}",
            )
            self._vector_enabled = True
        except Exception:
            self._vector_store = None
            self._vector_enabled = False

    # ── 检索 ──────────────────────────────────────────────

    def retrieve(self, query: str, limit: int = 5) -> list[RetrievalResult]:
        """LangChain + Chroma 优先，TF-IDF 兜底检索。

        Returns:
            list[RetrievalResult] — 按 score 降序，含 source_id/source_name/snippet/score。
        """
        vector_results = self._retrieve_with_chroma(query, limit)
        if vector_results:
            return vector_results

        return self._retrieve_with_tfidf(query, limit)

    def _retrieve_with_chroma(self, query: str, limit: int) -> list[RetrievalResult]:
        """通过 Chroma similarity_search_with_relevance_scores 检索。"""
        if not self._vector_enabled or self._vector_store is None:
            return []

        try:
            raw_results = self._vector_store.similarity_search_with_score(
                query, k=limit
            )
        except Exception:
            return []

        results: list[RetrievalResult] = []
        for doc, score in raw_results:
            metadata = doc.metadata or {}
            source_id = str(metadata.get("source_id", ""))
            source = self.sources.get(source_id)
            distance = max(0.0, float(score))
            normalized_score = 1.0 / (1.0 + distance)
            results.append(
                RetrievalResult(
                    source_id=source_id,
                    source_name=str(metadata.get("source_name", "")),
                    source_type=source.source_type if source else "document",
                    snippet=doc.page_content[:200].replace("\n", " ").strip(),
                    score=round(normalized_score, 4),
                    chunk_id=str(metadata.get("chunk_id", "")),
                    heading=str(metadata.get("heading", "")),
                )
            )

        return [r for r in results if r.source_id and r.snippet]

    def _retrieve_with_tfidf(self, query: str, limit: int) -> list[RetrievalResult]:
        """关键词 + TF-IDF 余弦相似度检索。"""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return self._fallback_results(limit)

        # 计算查询向量
        query_vec: dict[str, float] = {}
        for t in query_tokens:
            query_vec[t] = query_vec.get(t, 0.0) + 1.0 * self._idf.get(t, 1.0)

        # 与每个 chunk 计算余弦相似度
        scored: list[tuple[KnowledgeChunk, float]] = []
        for ch in self.chunks:
            ch_tf = self._term_index.get(ch.chunk_id, {})
            score = self._cosine_similarity(query_vec, ch_tf)
            if score > 0.0:
                scored.append((ch, score))

        # 关键词兜底：在 chunk content 中直接匹配 query 中的中文词
        for ch in self.chunks:
            if any(kw in ch.content for kw in query_tokens if len(kw) >= 2):
                already = any(s[0].chunk_id == ch.chunk_id for s in scored)
                if not already:
                    scored.append((ch, 0.15))

        scored.sort(key=lambda x: x[1], reverse=True)

        results: list[RetrievalResult] = []
        for ch, score in scored[:limit]:
            source = self.sources.get(ch.source_id)
            snippet = ch.content[:200].replace("\n", " ").strip()
            results.append(
                RetrievalResult(
                    source_id=ch.source_id,
                    source_name=ch.source_name,
                    source_type=source.source_type if source else "document",
                    snippet=snippet,
                    score=round(score, 4),
                    chunk_id=ch.chunk_id,
                    heading=ch.heading,
                )
            )

        if not results:
            return self._fallback_results(limit)

        return results

    def _cosine_similarity(
        self, query_vec: dict[str, float], doc_tf: dict[str, int]
    ) -> float:
        """计算查询向量与文档向量的余弦相似度。"""
        dot = 0.0
        norm_q = 0.0
        norm_d = 0.0

        for term, q_weight in query_vec.items():
            norm_q += q_weight * q_weight
            if term in doc_tf:
                d_weight = doc_tf[term] * self._idf.get(term, 1.0)
                dot += q_weight * d_weight

        for d_weight_raw in doc_tf.values():
            d_weight = d_weight_raw * self._idf.get(
                "", 1.0
            )  # simplified — use term lookup
            norm_d += d_weight * d_weight
        # correct norm_d
        norm_d = 0.0
        for term, tf in doc_tf.items():
            d_weight = tf * self._idf.get(term, 1.0)
            norm_d += d_weight * d_weight

        if norm_q == 0.0 or norm_d == 0.0:
            return 0.0
        return dot / ((norm_q**0.5) * (norm_d**0.5))

    def _fallback_results(self, limit: int) -> list[RetrievalResult]:
        """无匹配时返回文档开头片段。"""
        results: list[RetrievalResult] = []
        for ch in self.chunks[:limit]:
            source = self.sources.get(ch.source_id)
            results.append(
                RetrievalResult(
                    source_id=ch.source_id,
                    source_name=ch.source_name,
                    source_type=source.source_type if source else "document",
                    snippet=ch.content[:200].replace("\n", " ").strip(),
                    score=0.05,
                    chunk_id=ch.chunk_id,
                    heading=ch.heading,
                )
            )
        return results

    # ── 案例沉淀 ──────────────────────────────────────────

    def add_case(
        self,
        request_text: str,
        agent_name: str,
        decision: str,
        summary: str,
        evidence: list[str],
        next_actions: list[str],
        execution_mode: str = "single",
    ) -> CaseMemory:
        """将执行结果沉淀为可检索案例。"""
        case = CaseMemory(
            request_text=request_text,
            agent_name=agent_name,
            decision=decision,
            summary=summary,
            evidence=evidence,
            next_actions=next_actions,
            execution_mode=execution_mode,
        )
        self.cases.append(case)

        # 同时将案例入索引
        case_text = " ".join(
            [request_text, decision, summary, " ".join(evidence), " ".join(next_actions)]
        )
        chunk = KnowledgeChunk(
            source_id=f"case:{case.case_id}",
            source_name=f"案例:{agent_name}",
            heading=decision,
            content=case_text,
            char_count=len(case_text),
        )
        self.chunks.append(chunk)
        self.sources[chunk.source_id] = KnowledgeSource(
            source_id=chunk.source_id,
            source_name=chunk.source_name,
            source_type="agent_case",
        )

        if (
            self._vector_enabled
            and self._vector_store is not None
            and Document is not None
        ):
            try:
                self._vector_store.add_documents(
                    [
                        Document(
                            page_content=chunk.content,
                            metadata={
                                "source_id": chunk.source_id,
                                "source_name": chunk.source_name,
                                "chunk_id": chunk.chunk_id,
                                "heading": chunk.heading,
                            },
                        )
                    ]
                )
            except Exception:
                self._vector_enabled = False

        # 简单重建 term_index（可优化为增量）
        tokens = self._tokenize(case_text)
        tf = Counter(tokens)
        self._term_index[self.chunks[-1].chunk_id] = dict(tf)
        for term in set(tokens):
            self._idf[term] = self._idf.get(term, 0.0) + 0.1

        return case

    def search_cases(
        self, query: str, limit: int = 5
    ) -> list[CaseMemory]:
        """检索已沉淀的案例。"""
        scored: list[tuple[CaseMemory, float]] = []

        for case in self.cases:
            score = 0.0
            # 关键词匹配
            for token in self._tokenize(query):
                if len(token) < 2:
                    continue
                if token in case.request_text.lower():
                    score += 0.3
                if token in case.summary.lower():
                    score += 0.2
                if token in case.decision.lower():
                    score += 0.2
                if any(token in e.lower() for e in case.evidence):
                    score += 0.15
                if any(token in a.lower() for a in case.next_actions):
                    score += 0.1
            if score > 0:
                scored.append((case, min(score, 1.0)))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [case for case, _ in scored[:limit]]

    # ── 查询 ──────────────────────────────────────────────

    def get_source(self, source_id: str) -> KnowledgeSource | None:
        return self.sources.get(source_id)

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    @property
    def case_count(self) -> int:
        return len(self.cases)
