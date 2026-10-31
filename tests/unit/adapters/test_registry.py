import pytest

from tunedex.adapters.errors import UnknownAdapterError
from tunedex.adapters.m3u import M3UAdapter
from tunedex.adapters.registry import get_adapter, list_adapters


def test_lookup_by_name() -> None:
    adapter = get_adapter("m3u")
    assert isinstance(adapter, M3UAdapter)
    assert adapter.name == "m3u"


def test_unknown_adapter_lists_available() -> None:
    with pytest.raises(UnknownAdapterError, match="m3u") as excinfo:
        get_adapter("serato")
    assert excinfo.value.available == list_adapters() == ["m3u", "mixxx"]
