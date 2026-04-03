from app.reporting.asset_type import classify_asset_type


def test_classify_asset_type_handles_crypto_and_stocks() -> None:
    assert classify_asset_type(" BTC ") == "crypto"
    assert classify_asset_type("btc-usd") == "crypto"
    assert classify_asset_type("ABC-USD") == "stocks"
    assert classify_asset_type("NVDA") == "stocks"
    assert classify_asset_type(None) == "stocks"
