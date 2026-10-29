import socket
from collections.abc import Iterator

import pytest


class NetworkBlockedError(OSError):
    pass


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No command may open a connection; ``djlib enrich`` tests use a fake transport."""

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise NetworkBlockedError("network access in a CLI test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    yield
