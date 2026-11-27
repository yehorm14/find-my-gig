"""Test runner that keeps the suite fully offline.

Any outbound network attempt during tests raises instead of silently falling
back, and no real geocoding credential leaks in from the environment.
Tests that need a provider response must mock ``requests.get`` explicitly.
"""
import socket
from unittest import mock

from django.test.runner import DiscoverRunner


class NetworkBlockedError(AssertionError):
    """Raised when a test tries to reach the network."""


def _blocked_send(self, request, **kwargs):
    raise NetworkBlockedError(f"Unexpected outbound HTTP request in tests: {request.method} {request.url}")


_real_connect = socket.socket.connect


def _guarded_connect(self, address):
    # Allow local (unix) sockets and loopback; block everything else.
    if self.family in (socket.AF_INET, socket.AF_INET6):
        host = address[0]
        if host not in ("127.0.0.1", "::1", "localhost"):
            raise NetworkBlockedError(f"Unexpected outbound connection in tests: {address!r}")
    return _real_connect(self, address)


class OfflineDiscoverRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        from django.conf import settings

        self._offline_patches = [
            mock.patch("requests.sessions.Session.send", _blocked_send),
            mock.patch.object(socket.socket, "connect", _guarded_connect),
            # Never use a real credential from the environment in tests.
            mock.patch.object(settings, "GOOGLE_MAPS_BACKEND_KEY", None),
        ]
        for patcher in self._offline_patches:
            patcher.start()

    def teardown_test_environment(self, **kwargs):
        for patcher in reversed(self._offline_patches):
            patcher.stop()
        super().teardown_test_environment(**kwargs)
