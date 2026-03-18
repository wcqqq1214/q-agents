#!/usr/bin/env python
"""Test script to verify LLM and embedding configuration."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

def test_llm_config():
    """Test LLM configuration."""
    print("Testing LLM Configuration...")
    print("-" * 50)

    from app.llm_config import get_llm_provider, LLMProvider

    provider = get_llm_provider()
    print(f"✓ LLM Provider: {provider.value}")

    # Check if required API key is set
    if provider == LLMProvider.MINIMAX:
        key = os.getenv("MINIMAX_API_KEY")
        print(f"  MINIMAX_API_KEY: {'✓ Set' if key else '✗ Not set'}")
    elif provider == LLMProvider.OPENAI:
        key = os.getenv("OPENAI_API_KEY")
        print(f"  OPENAI_API_KEY: {'✓ Set' if key else '✗ Not set'}")
    elif provider == LLMProvider.GEMINI:
        key = os.getenv("GEMINI_API_KEY")
        print(f"  GEMINI_API_KEY: {'✓ Set' if key else '✗ Not set'}")
    elif provider == LLMProvider.CLAUDE:
        key = os.getenv("CLAUDE_API_KEY")
        print(f"  CLAUDE_API_KEY: {'✓ Set' if key else '✗ Not set'}")

    try:
        from app.llm_config import create_llm
        llm = create_llm()
        print(f"✓ LLM instance created successfully")
        print(f"  Model: {llm.model_name if hasattr(llm, 'model_name') else 'N/A'}")
    except Exception as e:
        print(f"✗ Failed to create LLM: {e}")

    print()


def test_embedding_config():
    """Test embedding configuration."""
    print("Testing Embedding Configuration...")
    print("-" * 50)

    from app.embedding_config import get_embedding_provider, EmbeddingProvider

    provider = get_embedding_provider()
    print(f"✓ Embedding Provider: {provider.value}")

    # Check if required API key is set
    if provider == EmbeddingProvider.MINIMAX:
        key = os.getenv("MINIMAX_API_KEY")
        print(f"  MINIMAX_API_KEY: {'✓ Set' if key else '✗ Not set'}")
    elif provider == EmbeddingProvider.OPENAI:
        key = os.getenv("OPENAI_API_KEY")
        print(f"  OPENAI_API_KEY: {'✓ Set' if key else '✗ Not set'}")

    try:
        from app.embedding_config import create_embeddings
        embeddings = create_embeddings()
        print(f"✓ Embeddings instance created successfully")
        print(f"  Model: {embeddings.model if hasattr(embeddings, 'model') else 'N/A'}")
    except Exception as e:
        print(f"✗ Failed to create embeddings: {e}")

    print()


def main():
    """Run all tests."""
    print("\n" + "=" * 50)
    print("LLM & Embedding Configuration Test")
    print("=" * 50 + "\n")

    test_llm_config()
    test_embedding_config()

    print("=" * 50)
    print("Test completed!")
    print("=" * 50 + "\n")


if __name__ == "__main__":
    main()
