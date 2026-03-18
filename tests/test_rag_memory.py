from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pytest

from app.rag.build_event_memory import create_memory_document, init_chroma_db
from app.rag.rag_tools import search_historical_event_impact


class FakeEmbeddings:
    """Deterministic fake embeddings for tests.

    This implementation avoids any external API calls while still producing
    stable vectors so that Chroma can build an index.
    """

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed_one(text)

    @staticmethod
    def _embed_one(text: str) -> List[float]:
        # Simple hash-based embedding: deterministic but meaningless.
        h = hash(text)
        rng = np.random.default_rng(abs(h) % (2**32))
        vec = rng.standard_normal(16).astype(float)
        return vec.tolist()


@pytest.fixture()
def tmp_chroma_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a temporary Chroma directory and patch env for the tools."""

    directory = tmp_path / "chroma_db"
    directory.mkdir()

    # Ensure rag_tools will look at this temporary directory.
    monkeypatch.setenv("EVENT_MEMORY_DB_DIR", str(directory))
    return directory


def test_init_chroma_db_and_metadata(tmp_chroma_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """init_chroma_db should persist docs with correct metadata."""

    # Patch OpenAIEmbeddings used inside init_chroma_db to avoid network calls.
    import app.rag.build_event_memory as bm

    monkeypatch.setattr(bm, "OpenAIEmbeddings", lambda: FakeEmbeddings())

    docs = [
        create_memory_document(
            ticker="NVDA",
            date="2024-01-01",
            news_summary="NVDA Q2 earnings beat expectations.",
            returns={"t1_return": 0.12, "t5_return": 0.18},
        ),
        create_memory_document(
            ticker="META",
            date="2024-02-01",
            news_summary="META Q4 earnings in line with expectations.",
            returns={"t1_return": -0.05, "t5_return": -0.02},
        ),
    ]
    metadatas: List[Dict[str, str]] = [
        {"ticker": "NVDA", "date": "2024-01-01", "event_type": "earnings"},
        {"ticker": "META", "date": "2024-02-01", "event_type": "earnings"},
    ]

    init_chroma_db(docs=docs, metadatas=metadatas, persist_directory=str(tmp_chroma_dir))

    # Lazy import to avoid bringing in Chroma when not needed.
    from langchain_chroma import Chroma  # type: ignore[import]

    store = Chroma(
        embedding_function=FakeEmbeddings(),
        persist_directory=str(tmp_chroma_dir),
        collection_name="event_memory",
    )
    retrieved = store.get(include=["metadatas"])

    assert len(retrieved.get("ids", [])) == 2
    stored_metas = retrieved.get("metadatas", [])
    assert any(m.get("ticker") == "NVDA" for m in stored_metas)
    assert any(m.get("ticker") == "META" for m in stored_metas)


def test_search_historical_event_impact_filters_by_ticker(
    tmp_chroma_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tool should return only NVDA events when queried for NVDA."""

    # Prepare a small mixed NVDA/META store using FakeEmbeddings.
    import app.rag.build_event_memory as bm

    monkeypatch.setattr(bm, "OpenAIEmbeddings", lambda: FakeEmbeddings())

    docs = [
        create_memory_document(
            ticker="NVDA",
            date="2024-01-01",
            news_summary="NVDA Q2 earnings beat expectations.",
            returns={"t1_return": 0.12, "t5_return": 0.18},
        ),
        create_memory_document(
            ticker="NVDA",
            date="2024-03-01",
            news_summary="NVDA raises Q3 guidance.",
            returns={"t1_return": 0.08, "t5_return": 0.15},
        ),
        create_memory_document(
            ticker="META",
            date="2024-02-01",
            news_summary="META Q4 earnings miss expectations.",
            returns={"t1_return": -0.10, "t5_return": -0.20},
        ),
    ]
    metadatas: List[Dict[str, str]] = [
        {"ticker": "NVDA", "date": "2024-01-01", "event_type": "earnings"},
        {"ticker": "NVDA", "date": "2024-03-01", "event_type": "earnings"},
        {"ticker": "META", "date": "2024-02-01", "event_type": "earnings"},
    ]

    init_chroma_db(docs=docs, metadatas=metadatas, persist_directory=str(tmp_chroma_dir))

    # Patch OpenAIEmbeddings used inside rag_tools loader.
    import app.rag.rag_tools as rt

    monkeypatch.setattr(rt, "OpenAIEmbeddings", lambda: FakeEmbeddings())

    result = search_historical_event_impact("earnings beat", "NVDA")
    assert "NVDA" in result
    assert "META" not in result
    assert "T+1" in result or "次日" in result


def test_search_historical_event_impact_no_matches(
    tmp_chroma_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When there is no ticker match, tool should return a graceful message."""

    # Initialize an empty or unrelated store.
    import app.rag.build_event_memory as bm

    monkeypatch.setattr(bm, "OpenAIEmbeddings", lambda: FakeEmbeddings())

    docs = [
        create_memory_document(
            ticker="META",
            date="2024-02-01",
            news_summary="META Q4 earnings miss expectations.",
            returns={"t1_return": -0.10, "t5_return": -0.20},
        ),
    ]
    metadatas: List[Dict[str, str]] = [
        {"ticker": "META", "date": "2024-02-01", "event_type": "earnings"},
    ]
    init_chroma_db(docs=docs, metadatas=metadatas, persist_directory=str(tmp_chroma_dir))

    import app.rag.rag_tools as rt

    monkeypatch.setattr(rt, "OpenAIEmbeddings", lambda: FakeEmbeddings())

    result = search_historical_event_impact("earnings beat", "TSLA")
    assert "未能在历史事件记忆库中找到" in result

