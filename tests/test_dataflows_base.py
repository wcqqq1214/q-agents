# tests/test_dataflows_base.py
import pytest
from app.dataflows.base import BaseDataProvider, ProviderError, ProviderTimeoutError

def test_provider_error_hierarchy():
    """Test exception hierarchy"""
    assert issubclass(ProviderTimeoutError, ProviderError)
    assert issubclass(ProviderError, Exception)

def test_base_provider_is_abstract():
    """Test BaseDataProvider cannot be instantiated"""
    with pytest.raises(TypeError):
        BaseDataProvider({})
