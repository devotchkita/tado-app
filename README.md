# Tado Control

A better Tado thermostat interface built with Streamlit.

## What it does

- **Dashboard**: All rooms at a glance with current temp, target, heating status, humidity, battery
- **Global Override**: Set all rooms to one temperature with one click, or resume all schedules
- **Seasonal Profiles**: Save your current schedule as "Winter", "Summer" etc. Switch with one tap instead of editing room-by-room
- **Devices & Offsets**: See battery status and adjust temperature offsets to compensate for radiator-adjacent readings

## Setup

### Local

```bash
pip install -r requirements.txt
streamlit run app.py
```

First run: click "Start Login" and follow the OAuth2 device code flow in your browser.

### Streamlit Cloud

1. Push this repo to GitHub
2. Deploy on [share.streamlit.io](https://share.streamlit.io)
3. First visit: log in via the device code flow
4. Copy your refresh token from the sidebar Connection panel
5. Add it to Streamlit Cloud secrets as `TADO_REFRESH_TOKEN = "your-token"`
6. The app will auto-reconnect on restarts

## Seasonal profiles

Profiles are saved as JSON files in the `profiles/` directory. On Streamlit Cloud,
these reset on redeploy. For persistence, commit your profiles to the repo after saving.

Locally they persist between runs.
