from __future__ import annotations

import os

from dotenv import load_dotenv
from langchain_community.embeddings.minimax import MiniMaxEmbeddings


def test_embedding() -> None:
    """Simple smoke test for the MiniMax embedding backend configuration."""

    # Ensure .env is loaded so that MINIMAX_API_KEY / MINIMAX_GROUP_ID are visible.
    load_dotenv()

    model = os.getenv("EMBEDDING_MODEL_NAME", "embo-01")

    print(f"Using MiniMax embedding model={model!r}")

    try:
        embeddings = MiniMaxEmbeddings(model=model)
        print("Sending test embedding request...")
        vec = embeddings.embed_query("这是一条测试新闻文本。")
        print(f"✅ Success: received embedding with dimension {len(vec)}")
    except Exception as exc:  # noqa: BLE001
        print(f"❌ Failed to get embedding: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    test_embedding()

