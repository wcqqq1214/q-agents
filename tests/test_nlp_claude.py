"""Test NLP tools with Claude provider."""

import os

from dotenv import load_dotenv

load_dotenv()


def test_analyze_reddit_text():
    """Test analyze_reddit_text with Claude provider."""
    print("\n=== Testing analyze_reddit_text with Claude ===")
    print(f"LLM Provider: {os.environ.get('LLM_PROVIDER')}")

    from app.social.nlp_tools import analyze_reddit_text

    # Test with sample Reddit text
    sample_text = """
    NVDA is going to the moon! 🚀
    Just bought more shares, this AI boom is insane.
    Jensen Huang is a genius, new GPUs are selling out everywhere.
    Some people are worried about valuation but I think we're still early.
    """

    try:
        result = analyze_reddit_text.invoke({"asset": "NVDA", "text": sample_text})

        print("\n✓ Analysis completed successfully")
        print(f"  Sentiment: {result['sentiment']}")
        print(f"  Keywords: {result['keywords']}")
        print(f"  Summary: {result['summary']}")

        # Validate result structure
        assert result["sentiment"] in [
            "panic",
            "bearish",
            "neutral",
            "bullish",
            "euphoric",
        ]
        assert isinstance(result["keywords"], list)
        assert isinstance(result["summary"], str)
        assert len(result["summary"]) > 0

        print("\n✓ Result structure is valid")
        return True

    except Exception as exc:
        print(f"\n✗ Test failed: {exc}")
        import traceback

        traceback.print_exc()
        return False


def test_empty_text_handling():
    """Test graceful handling of empty text."""
    print("\n=== Testing Empty Text Handling ===")

    from app.social.nlp_tools import analyze_reddit_text

    try:
        result = analyze_reddit_text.invoke(
            {"asset": "BTC", "text": "No posts fetched from Reddit"}
        )

        print("✓ Empty text handled gracefully")
        print(f"  Sentiment: {result['sentiment']}")
        print(f"  Summary: {result['summary']}")

        assert result["sentiment"] == "neutral"
        assert "No Reddit discussion" in result["summary"]

        return True

    except Exception as exc:
        print(f"✗ Test failed: {exc}")
        return False


if __name__ == "__main__":
    print("Testing NLP Tools with Claude Provider")
    print("=" * 60)

    results = []
    results.append(("Analyze Reddit Text", test_analyze_reddit_text()))
    results.append(("Empty Text Handling", test_empty_text_handling()))

    print("\n" + "=" * 60)
    print("Test Summary:")
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: {name}")

    all_passed = all(r[1] for r in results)
    print("=" * 60)
    if all_passed:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed")
        exit(1)
