"""
E2E test fixtures for mammotion_lite.

Manages HA Docker container lifecycle, onboarding, and REST API client.
The integration can't connect to the real Mammotion cloud in E2E,
but we verify it loads gracefully (cloud retry) and entities exist.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

import pytest

# E2E tests need real network access to Docker
try:
    import pytest_socket

    def _restore_sockets():
        import socket as _socket
        pytest_socket.enable_socket()
        if hasattr(pytest_socket, "_true_connect"):
            _socket.socket.connect = pytest_socket._true_connect
except ImportError:
    def _restore_sockets():
        pass


@pytest.fixture(scope="session", autouse=True)
def _allow_sockets_session():
    _restore_sockets()
    yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations():
    """Override root conftest - E2E tests don't use in-process HA."""
    _restore_sockets()
    yield


# Override the verify_cleanup fixture from root conftest - not applicable to E2E
@pytest.fixture(autouse=True)
def verify_cleanup():
    yield


# Override _register_custom_component from root conftest - not applicable to E2E
@pytest.fixture(autouse=True)
def _register_custom_component():
    yield


E2E_HA_PORT = 18124  # Different from rain_incoming's 18123
HA_URL = f"http://localhost:{E2E_HA_PORT}"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".e2e-token")

_DOCKER_ENV = {
    "HA_CONTAINER": "ha-mammotion-e2e",
    "HA_VOLUME": "ha-mammotion-e2e-config",
    "HA_PORT": str(E2E_HA_PORT),
}

_E2E_DOCKER_VOLUME = f"mammotion-lite_{_DOCKER_ENV['HA_VOLUME']}"


class HAClient:
    """Simple REST client for the HA instance."""

    def __init__(self, token: str) -> None:
        self.token = token

    def request(self, method: str, path: str, data: dict | None = None) -> dict | None:
        url = f"{HA_URL}{path}"
        headers = {"Authorization": f"Bearer {self.token}"}
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            raise RuntimeError(f"HTTP {e.code} on {method} {path}: {raw[:300]}") from e

    def get_state(self, entity_id: str) -> dict | None:
        try:
            return self.request("GET", f"/api/states/{entity_id}")
        except RuntimeError:
            return None

    def poll_entity_state(
        self,
        entity_id: str,
        *,
        timeout: float = 60,
        interval: float = 2.0,
        condition=None,
    ) -> dict:
        """Poll entity until it exists and optionally meets a condition."""
        deadline = time.time() + timeout
        last_state = None
        while time.time() < deadline:
            state = self.get_state(entity_id)
            if state is not None:
                if condition is None or condition(state):
                    return state
                last_state = state
            time.sleep(interval)
        if last_state is not None:
            raise TimeoutError(
                f"Entity {entity_id} exists but condition not met within {timeout}s. "
                f"Last state: {last_state.get('state')}"
            )
        raise TimeoutError(f"Entity {entity_id} not found within {timeout}s")


def _wait_for(url: str, timeout: int = 120) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url)
            urllib.request.urlopen(req, timeout=2)
            return
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return
            time.sleep(1)
        except (urllib.error.URLError, OSError):
            time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {url}")


@pytest.fixture(scope="session")
def ha_container():
    """Ensure HA container is running with mammotion_lite installed."""
    compose_file = os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.dev.yml")
    env = {**os.environ, **_DOCKER_ENV}

    # Clean start
    subprocess.run(
        ["docker", "compose", "-f", compose_file, "down"],
        capture_output=True, env=env,
    )
    subprocess.run(
        ["docker", "volume", "rm", "-f", _E2E_DOCKER_VOLUME],
        capture_output=True,
    )
    try:
        os.remove(TOKEN_FILE)
    except FileNotFoundError:
        pass

    subprocess.run(
        ["docker", "compose", "-f", compose_file, "up", "-d"],
        capture_output=True, env=env, check=True,
    )
    _wait_for(f"{HA_URL}/api/", timeout=120)
    time.sleep(10)  # let HA finish initial setup
    yield

    # Leave running for inspection


@pytest.fixture(scope="session")
def ha_client(ha_container) -> HAClient:
    """Onboard HA and return a REST client with a valid auth token."""
    # Try cached token
    try:
        with open(TOKEN_FILE) as f:
            token = f.read().strip()
        client = HAClient(token)
        client.request("GET", "/api/")
        return client
    except (FileNotFoundError, RuntimeError):
        pass

    def _raw_request(method, path, data=None, token=None, form=False):
        url = f"{HA_URL}{path}"
        headers = {}
        body = None
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if data is not None:
            if form:
                body = urllib.parse.urlencode(data).encode()
                headers["Content-Type"] = "application/x-www-form-urlencoded"
            else:
                body = json.dumps(data).encode()
                headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}

    def _get_token_via_login():
        flow = _raw_request("POST", "/auth/login_flow", {
            "client_id": f"{HA_URL}/",
            "handler": ["homeassistant", None],
            "redirect_uri": f"{HA_URL}/",
        })
        result = _raw_request("POST", f"/auth/login_flow/{flow['flow_id']}", {
            "username": "dev", "password": "devdevdev",
            "client_id": f"{HA_URL}/",
        })
        token_resp = _raw_request("POST", "/auth/token", {
            "client_id": f"{HA_URL}/",
            "grant_type": "authorization_code",
            "code": result["result"],
        }, form=True)
        return token_resp["access_token"]

    # Check onboarding status
    try:
        onboarding = _raw_request("GET", "/api/onboarding")
    except Exception:
        onboarding = None

    if onboarding and "user" in [s["step"] for s in onboarding]:
        resp = _raw_request("POST", "/api/onboarding/users", {
            "client_id": f"{HA_URL}/",
            "name": "E2E Test", "username": "dev",
            "password": "devdevdev", "language": "en",
        })
        token_resp = _raw_request("POST", "/auth/token", {
            "client_id": f"{HA_URL}/",
            "grant_type": "authorization_code",
            "code": resp["auth_code"],
        }, form=True)
        token = token_resp["access_token"]
        _raw_request("POST", "/api/onboarding/core_config", {
            "latitude": -33.701, "longitude": 151.209,
            "country": "AU", "time_zone": "Australia/Sydney",
            "elevation": 200, "unit_system": "metric",
            "currency": "AUD", "language": "en",
        }, token=token)
        _raw_request("POST", "/api/onboarding/analytics", {}, token=token)
        _raw_request("POST", "/api/onboarding/integration", {
            "client_id": f"{HA_URL}/",
            "redirect_uri": f"{HA_URL}/?auth_callback=1",
        }, token=token)
    else:
        token = _get_token_via_login()

    with open(TOKEN_FILE, "w") as f:
        f.write(token)

    return HAClient(token)
