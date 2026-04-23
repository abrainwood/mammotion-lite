# Mammotion Lite

[![CI](https://github.com/abrainwood/mammotion-lite/actions/workflows/ci.yml/badge.svg)](https://github.com/abrainwood/mammotion-lite/actions/workflows/ci.yml)
[![Quality Gate](https://sonarcloud.io/api/project_badges/measure?project=abrainwood_mammotion-lite&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=abrainwood_mammotion-lite)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=abrainwood_mammotion-lite&metric=coverage)](https://sonarcloud.io/summary/new_code?id=abrainwood_mammotion-lite)
[![Maintainability](https://sonarcloud.io/api/project_badges/measure?project=abrainwood_mammotion-lite&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=abrainwood_mammotion-lite)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[![Click to open this repository inside your own Home Assistant HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=abrainwood&repository=mammotion-lite&category=Integration)

> **Note:** The polling issues that originally motivated this project have since been addressed in the full [Mammotion-HA](https://github.com/mikey0000/Mammotion-HA) integration. If you want full mower control (start/stop, scheduling, zone management, BLE, firmware updates), use Mammotion-HA. Use this integration if you just want camera and basic sensors/statistics with a minimal footprint.

> **Alpha** - this integration is under active development. It's in daily use on a Luba 2 AWD 1500 and works well, but hasn't been tested on other Mammotion models. If you try it, feedback is welcome - especially on other mower models, camera stability, or event codes I haven't seen yet. [Open an issue](https://github.com/abrainwood/mammotion-lite/issues).

**Lightweight Mammotion mower integration for Home Assistant.** Passive sensors, event-driven reporting, and on-demand camera streaming - read-only, with near-zero impact on your mower's battery and navigation.

---

## Entities you get

On demand: 
- **Camera** - WebRTC streaming via Agora custom Lovelace card

Updated in real-time from existing mower update pushes:
- **Last event** - task started, completed, returning, docked (with code and timestamp)
- **Activity** - mowing, returning, docked, charging - driven by real-time notification events
- **Online/offline** - real-time connectivity status

Updates every 60 seconds during mowing, every 30 minutes when idle:
- **Battery**
- **WiFi signal**
- **Job progress**
- **Blade height**
- **GPS location**


---

## Why "Lite"?

| | Mammotion-HA | Mammotion Lite |
|---|---|---|
| Mower controls | Start, stop, pause, dock, scheduling, zone management | None - use the Mammotion app for control |
| Sensor updates during mowing | Every few seconds | Every 60 seconds |
| Commands per mow session | Hundreds | ~5 |
| Idle impact | Continuous polling, interrupts sleep | Zero (passive 30-min pushes) |
| Battery/navigation impact | Reported by some users | None observed |
| BLE support | Yes | No (cloud only) |
| Firmware updates | Yes | No |
| Map sync | Yes | No |

**How it works:** Instead of polling, the integration listens for MQTT push events from the Mammotion cloud. When the mower starts a task (event code 1301), we send a single command to enable 60-second reporting. When it docks (event code 1307), we stop reporting. A keepalive renews the subscription every 2 minutes during mowing to recover from app interference. Between mows, we receive passive 30-minute property pushes with no commands sent at all.

**Tradeoffs:** This integration is deliberately read-only - you can't start, stop, or control the mower from HA. Use the Mammotion app for that. You also don't get map sync, firmware updates, scheduling, zone management, or BLE connectivity. What you do get is reliable sensor data and camera streaming without interfering with your mower's operation or the app's functionality. If you need full control, the [Mammotion-HA](https://github.com/mikey0000/Mammotion-HA) integration is the right choice - this integration is for people who primarily want visibility without the side effects.

---

## Installation

### Method 1: HACS (recommended)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

1. Make sure [HACS](https://hacs.xyz) is installed
2. In HACS, click the three-dot menu (top right) and choose **Custom repositories**
3. Add `https://github.com/abrainwood/mammotion-lite` as an **Integration**
4. Find **Mammotion Lite** in the HACS list and click **Download**
5. Restart Home Assistant
6. Go to **Settings > Integrations > Add Integration** and search for **"Mammotion Lite"**

### Method 2: Manual

1. Download the latest release from [GitHub](https://github.com/abrainwood/mammotion-lite/releases)
2. Copy the `custom_components/mammotion_lite` folder into your `config/custom_components/` directory
3. Restart Home Assistant
4. Go to **Settings > Integrations > Add Integration** and search for **"Mammotion Lite"**

---

## Configuration

No YAML needed - everything is configured through the Home Assistant UI.

1. Enter your Mammotion account email and password (recommend you use a dedicated account - see [Requirements](#requirements))
2. If you have multiple mowers, select which one to configure (multiple mowers haven't been tested - let me know if it works for you!)
3. That's it - sensors populate automatically

**Tested on:** Luba 2 AWD 1500. Other Mammotion models (Luba 1, Yuka) may work but haven't been tested - feedback welcome.

---

## Camera setup

The camera uses Agora WebRTC for streaming, handled entirely in the browser via a custom Lovelace card.

### Add the card resource

1. Go to **Settings > Dashboards > Resources**
2. Add `/mammotion_lite/agora-client.js` as a **JavaScript Module**

### Add the card to a dashboard

Use the custom card type `camera-agora-card`:

```yaml
type: custom:camera-agora-card
entity: camera.YOUR_MOWER_NAME_camera
```

The card provides play/stop/fullscreen controls and camera switching (left/right/rear where supported).

---

## Event codes

The integration tracks these notification event codes from the mower. Both 13xx and 12xx series have been observed with the same suffix meanings (the distinction between the two series is unclear - cancel sequences always use 12xx regardless of how the task was started). Unknown codes are logged at WARNING for investigation:

| Code | Label | RPT action |
|---|---|---|
| 1201 | Task started | Triggers RPT_START (begin reporting) |
| 1205 | Arrived at base | - |
| 1207 | Docked and charging | Triggers RPT_STOP (stop reporting) |
| 1301 | Task started | Triggers RPT_START (begin reporting) |
| 1302 | Task cancelled | - |
| 1304 | Returning to base | - |
| 1305 | Task completed | - |
| 1307 | Docked and charging | Triggers RPT_STOP (stop reporting) |

Codes 1303 and 1306 have been observed but their meaning is unconfirmed (likely error/stuck states).

---

## Troubleshooting

### Sensors show "unknown" after setup

The integration relies on push data from the Mammotion cloud. An initial probe is sent on startup to request a few reports, but full sensor data arrives with the next 30-minute property push or when the mower starts a task. Give it up to 30 minutes for idle-state sensors to populate.

### Camera doesn't work or shows "Connection error"

The camera requires the Agora custom lovelace card (included) and won't work by just viewing the entity directly. If you're having trouble try these things: 

1. Check that you've added the JS resource (`/mammotion_lite/agora-client.js`) in **Settings > Dashboards > Resources**
2. Make sure you're using the custom card type `camera-agora-card`, not the default camera card
3. Clear your browser cache (Lovelace caches JS aggressively)

### Cloud connection fails

The integration retries cloud connections in the background. If your Mammotion account credentials change, go to **Settings > Integrations > Mammotion Lite > Configure** to update them.

### pymammotion version conflict with Mammotion-HA

If you have both this integration and the full [Mammotion-HA](https://github.com/mikey0000/Mammotion-HA) integration installed, you may see errors like:

```
cannot import name 'MowerDevice' from 'pymammotion.data.model.device'
```

or

```
cannot import name 'RTKBaseStationDevice' from 'pymammotion.data.model.device'
```

This happens because both integrations depend on `pymammotion` but Home Assistant installs all dependencies into a single Python environment - only one version can exist at a time. If the two integrations pin different versions, whichever loads last overwrites the other.

**To fix:** Update both integrations to their latest versions (both should work with the same pymammotion version). If the issue persists, temporarily disable one integration, restart HA, then re-enable it.

---

## Requirements

- Home Assistant
- A **dedicated Mammotion account** for HA (recommended - see below)
- Internet access (Mammotion cloud + Agora for camera)

### Why use a separate account?

Using your primary Mammotion account for both the app and HA will cause the app to get signed out when HA connects. Create a second account and share your mower with it:

1. Create a new Mammotion account (email aliases like `you+ha@gmail.com` work well)
2. In the Mammotion app, go to your mower's settings and share it with the new account
3. Use the new account's credentials when configuring the integration in HA

---

## Contributing

Bug reports, feature requests, and PRs are welcome. The project uses TDD - see [CLAUDE.md](CLAUDE.md) for development setup and test instructions.

```bash
# Run tests
cd mammotion-lite
python -m pytest tests/unit tests/integration -v

# Run E2E (needs Docker)
python -m pytest tests/e2e/ -v
```

---

## License

[MIT](LICENSE)
