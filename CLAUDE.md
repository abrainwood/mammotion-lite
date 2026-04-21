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
- Event codes: 1301=task started, 1302=cancelled, 1304=returning, 1305=completed, 1307=docked/charging

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
