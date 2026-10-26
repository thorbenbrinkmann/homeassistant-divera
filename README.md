# DIVERA 24/7 for Home Assistant

Custom integration connecting [DIVERA 24/7](https://www.divera247.com/) accounts to Home Assistant.

All units (*Einheiten*) of the configured account and their vehicles are discovered automatically. Data updates arrive in real time via the DIVERA 24/7 WebSocket API, with a configurable polling fallback (60 seconds by default).

## Features

### Per Unit (Service Device)

- **Binary sensors:** Active alarm, alarm priority (*Sonderrechte*), alarm closed
- **Sensors:** Alarm keyword, alarm message (full text in `full_text` attribute), alarm address, alarm time, alerted vehicles, alarm ID (diagnostic, disabled by default)
- **Event:** Fires `new_alarm` when a new open alarm arrives and `alarm_closed` when an open alarm is closed
- **Select:** Set and view your own user availability status (*Statusgeber*) in the unit
- **Device tracker:** Map coordinates of the latest alarm

### Per Vehicle (Device)

- **Sensors:** FMS status (`0`–`9`), status note, status timestamp
- **Device tracker:** Map coordinates of the vehicle

## Installation

### Via Marketplace / HACS (Custom Repository)

1. Open **Settings** → **Marketplace** (or **HACS**) in Home Assistant.
2. Add `https://github.com/thorbenbrinkmann/homeassistant-divera` as a custom repository of type **Integration**.
3. Install **DIVERA 24/7**.

### Manual

Copy the `custom_components/divera` folder into your Home Assistant `config/custom_components/` directory and restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=divera)

1. In Home Assistant, go to **Settings** → **Devices & services** → **Add integration** and select **DIVERA 24/7**.
2. Enter your personal API access key (found in DIVERA 24/7 under **Settings** → **Login** → **API-Keys** / **Einstellungen** → **Login** → **API-Keys**).
