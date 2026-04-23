# mammotion_lite

Lightweight Mammotion mower integration for Home Assistant. Passive sensors + on-demand camera with near-zero mower impact.

## Architecture

- **No DataUpdateCoordinator** - push-driven via MQTT callbacks
- **Event-driven RPT_START/STOP** - `device_notification_event` codes trigger reporting, not polling
- **Camera via Agora JS card** - browser-side WebRTC, server provides token services
- **Graceful cloud degradation** - retry on failure, don't break the integration

## Key technical facts

- `user_account` passed to `MammotionCommand` MUST be `int`, not `str`
- Job progress percentage = `report_data.work.area >> 16` (NOT the `progress` field)
- Static files served via `async_setup` + `StaticPathConfig` (not `async_setup_entry`)
- RPT_START: period=60000ms, timeout=180000ms, keepalive every 120s
- Event codes: 13xx and 12xx series with same suffix meanings (distinction unclear)
  - x01=task started, x02=cancelled, x04=returning, x05=completed, x07=docked/charging
  - RPT_START triggered by 1301 and 1201; RPT_STOP triggered by 1307 and 1207
  - Unknown codes logged at WARNING for investigation
- Coordinate property push sends RTK values in radians (not degrees) - must convert with `* 180 / pi`
- Activity sensor uses EVENT_CODE_TO_ACTIVITY mapping (event codes take priority over snapshot)

## Development

```bash
# Run tests
cd ~/src/projects/homeassistant/mammotion-lite
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/unit/test_sensors.py -v

# Run with coverage
python -m pytest tests/ --cov=custom_components.mammotion_lite -v
```

## TDD rules

- Every production file is built test-first (red-green-refactor)
- Tests import constants from production code, never reconstruct them
- No `except Exception: pass` - all unexpected exceptions logged at WARNING+
- POC at `../custom_components/mammotion_camera/` is reference only - never copy-paste

## Dependencies

- pymammotion==0.7.55
- homeassistant (dev environment)
- pytest, pytest-asyncio, pytest-homeassistant-custom-component (test)
