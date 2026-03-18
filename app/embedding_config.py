"""Embedding configuration module."""

from __future__ import annotations

import os
from typing import List
import requests
from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings

load_dotenv()


class MinimaxEmbeddings(Embeddings):
    """MiniMax embeddings using native API format."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of documents."""
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "texts": texts,
                "type": "db"
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["vectors"]

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query."""
        response = requests.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": self.model,
                "texts": [text],
                "type": "query"
            }
        )
        response.raise_for_status()
        data = response.json()
        return data["vectors"][0]


def create_embeddings() -> Embeddings:
    """Create MiniMax embeddings instance."""
    api_key = os.environ.get("MINIMAX_API_KEY")
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY is not set.")

    base_url = os.environ.get("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
    model = os.environ.get("MINIMAX_EMBEDDING_MODEL", "embo-01")

    return MinimaxEmbeddings(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
