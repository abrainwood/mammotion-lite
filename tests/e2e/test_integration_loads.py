"""E2E tests: verify mammotion_lite loads in a real HA Docker instance.

These tests start a real HA container with the integration mounted,
onboard it, and verify the integration is discoverable. Since we can't
connect to the real Mammotion cloud, we verify:
1. The integration is recognized by HA (manifest loads)
2. The config flow is accessible via REST API
3. HA doesn't crash on startup with our code present
"""
from __future__ import annotations

import pytest

from tests.e2e.conftest import HAClient


class TestIntegrationLoads:
    """Verify the integration is loadable in a real HA instance."""

    def test_ha_is_running(self, ha_client: HAClient):
        """HA instance is responsive."""
        result = ha_client.request("GET", "/api/")
        assert result is not None
        assert result.get("message") == "API running."

    def test_mammotion_lite_config_flow_accessible(self, ha_client: HAClient):
        """The config flow handler for mammotion_lite is available."""
        # Start a config flow - this proves HA can load our config_flow.py
        try:
            flow = ha_client.request("POST", "/api/config/config_entries/flow", {
                "handler": "mammotion_lite",
            })
            assert flow is not None
            assert flow.get("type") == "form"
            assert flow.get("step_id") == "user"

            # Clean up - abort the flow
            ha_client.request(
                "DELETE",
                f"/api/config/config_entries/flow/{flow['flow_id']}",
            )
        except RuntimeError as e:
            pytest.fail(f"Config flow not accessible: {e}")

    def test_no_errors_in_ha_log_for_mammotion_lite(self, ha_client: HAClient):
        """No ERROR-level log entries for mammotion_lite on startup."""
        # Check HA error log
        try:
            result = ha_client.request("GET", "/api/error_log")
        except RuntimeError:
            pytest.skip("Error log endpoint not available")
            return

        if result and isinstance(result, str):
            lines = result.split("\n")
            mammotion_errors = [
                line for line in lines
                if "mammotion_lite" in line and "ERROR" in line
            ]
            assert mammotion_errors == [], f"Found errors: {mammotion_errors}"
