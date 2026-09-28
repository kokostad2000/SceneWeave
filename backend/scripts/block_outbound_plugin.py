"""交付核验用 pytest 插件：允许回环假服务，阻断出站 DNS 与连接。"""

import socket

import pytest

_LOOPBACK = {None, "", "127.0.0.1", "::1", "localhost"}


@pytest.fixture(autouse=True)
def block_outbound_network(monkeypatch):
    original_dns = socket.getaddrinfo
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex

    def dns(host, *args, **kwargs):
        if host not in _LOOPBACK:
            raise RuntimeError("交付核验阻断出站 DNS")
        return original_dns(host, *args, **kwargs)

    def guarded(original):
        def connect(sock, address):
            host = address[0] if isinstance(address, tuple) else None
            if host not in _LOOPBACK:
                raise RuntimeError("交付核验阻断出站连接")
            return original(sock, address)
        return connect

    monkeypatch.setattr(socket, "getaddrinfo", dns)
    monkeypatch.setattr(socket.socket, "connect", guarded(original_connect))
    monkeypatch.setattr(socket.socket, "connect_ex", guarded(original_connect_ex))
