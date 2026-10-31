"""Looking up format adapters by name."""

from collections.abc import Callable

from tunedex.adapters.contract import Adapter
from tunedex.adapters.errors import UnknownAdapterError


def _m3u() -> Adapter:
    from tunedex.adapters.m3u import M3UAdapter

    return M3UAdapter()


def _mixxx() -> Adapter:
    from tunedex.adapters.mixxx import MixxxAdapter

    return MixxxAdapter()


# Name -> factory for a default-configured adapter. Imports are lazy so that
# looking up one adapter does not load every format.
_FACTORIES: dict[str, Callable[[], Adapter]] = {"m3u": _m3u, "mixxx": _mixxx}


def list_adapters() -> list[str]:
    return sorted(_FACTORIES)


def get_adapter(name: str) -> Adapter:
    try:
        factory = _FACTORIES[name]
    except KeyError:
        raise UnknownAdapterError(name, list_adapters()) from None
    return factory()
