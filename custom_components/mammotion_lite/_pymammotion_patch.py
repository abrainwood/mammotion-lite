"""Monkey-patch pymammotion to send a real-device-shaped App-Version header.

Mammotion's id.mammotion.com/oauth2/token endpoint rejects pymammotion's
default `App-Version: ALIYUN DEMO,<x.y.z>` with `code=29003 msg='Access denied'`.
A real-Android-app-shaped value passes. Verified against APK
HttpConstants.APP_VERSION header format:
    <Brand> <Model> <Hardware>-Android <ver>,<AppVer>

Until upstream pymammotion changes its default header, applying this
patch at package import time is the cheapest workaround.
"""

from __future__ import annotations

from pymammotion.http.http import MammotionHTTP

_SPOOFED_APP_VERSION = "samsung SM_T733 qcom-Android 14,2.3.2.13"
_PATCH_FLAG = "_mammotion_lite_app_version_patched"


def _apply_patch() -> None:
    if getattr(MammotionHTTP, _PATCH_FLAG, False):
        return

    original_init = MammotionHTTP.__init__

    def patched_init(self, *args, **kwargs) -> None:
        original_init(self, *args, **kwargs)
        self._headers["App-Version"] = _SPOOFED_APP_VERSION

    MammotionHTTP.__init__ = patched_init
    setattr(MammotionHTTP, _PATCH_FLAG, True)


_apply_patch()
