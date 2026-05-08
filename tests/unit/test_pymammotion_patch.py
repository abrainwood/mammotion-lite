"""Verify the pymammotion App-Version monkey-patch is applied.

Mammotion's id.mammotion.com/oauth2/token endpoint rejects the default
pymammotion App-Version header (`ALIYUN DEMO,X.Y.Z`) with "Access denied".
We monkey-patch MammotionHTTP to send a real-device-shaped header instead.

This test imports our integration package (which applies the patch as a
side-effect) and then verifies a freshly-constructed MammotionHTTP carries
the spoofed header.
"""

from __future__ import annotations


class TestAppVersionHeaderPatch:
    """Verify the App-Version header is spoofed to a real-device shape."""

    def test_app_version_is_not_aliyun_demo(self):
        """Default 'ALIYUN DEMO,*' is blocked by the cloud - must be replaced."""
        # Import the package - applies the monkey-patch on first import
        import custom_components.mammotion_lite  # noqa: F401
        from pymammotion.http.http import MammotionHTTP

        http = MammotionHTTP()
        app_version = http._headers.get("App-Version", "")

        assert not app_version.startswith("ALIYUN DEMO"), (
            f"App-Version still starts with 'ALIYUN DEMO': {app_version!r}. "
            "The cloud will reject this with 'Access denied'."
        )

    def test_app_version_has_device_shape(self):
        """App-Version should look like '<Brand> <Model> <Hardware>-Android <Ver>,<AppVer>'."""
        import custom_components.mammotion_lite  # noqa: F401
        from pymammotion.http.http import MammotionHTTP

        http = MammotionHTTP()
        app_version = http._headers.get("App-Version", "")

        # Must have a comma separating device descriptor from app version
        assert "," in app_version, f"missing comma: {app_version!r}"
        device_part, app_part = app_version.rsplit(",", 1)
        # Device part must include "Android" so the gateway sees a phone-like UA
        assert "Android" in device_part, f"device part lacks 'Android': {device_part!r}"
        # App version part should look like a dotted version string
        assert app_part.count(".") >= 2, f"app version lacks dots: {app_part!r}"

    def test_user_agent_unchanged(self):
        """User-Agent stays as okhttp - the gateway doesn't filter on it."""
        import custom_components.mammotion_lite  # noqa: F401
        from pymammotion.http.http import MammotionHTTP

        http = MammotionHTTP()
        assert http._headers.get("User-Agent", "").startswith("okhttp/")
