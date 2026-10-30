import streamlit as st
import json
import os
import time
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Tado Control",
    page_icon="🌡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROFILES_DIR = Path(__file__).parent / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)
TOKEN_FILE = Path(__file__).parent / ".tado_token.json"

# ---------------------------------------------------------------------------
# Helpers – token persistence
# ---------------------------------------------------------------------------
# On Streamlit Cloud the filesystem resets between deploys, so we also
# let the user paste a refresh token from st.secrets or manually.


def _get_tado_client():
    """Return an authenticated Tado client or None."""
    from libtado.api import Tado

    # 1. Already authenticated this session
    if "tado" in st.session_state and st.session_state.tado is not None:
        try:
            st.session_state.tado.refresh_auth()
            return st.session_state.tado
        except Exception:
            st.session_state.tado = None

    # 2. Try saved refresh token (from secrets or file)
    refresh_token = None
    try:
        refresh_token = st.secrets["TADO_REFRESH_TOKEN"]
    except Exception:
        if TOKEN_FILE.exists():
            data = json.loads(TOKEN_FILE.read_text())
            refresh_token = data.get("refresh_token")

    if refresh_token:
        try:
            t = Tado(saved_refresh_token=refresh_token)
            status = t.get_device_activation_status()
            if status.name == "COMPLETED":
                t.device_ready()
                st.session_state.tado = t
                _persist_token(t)
                return t
        except Exception:
            pass

    return None


def _persist_token(tado_client):
    """Save refresh token to disk so it survives app restarts (locally)."""
    try:
        token_data = {
            "refresh_token": tado_client.refresh_token,
            "saved_at": datetime.now().isoformat(),
        }
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Helpers – profiles
# ---------------------------------------------------------------------------


def load_profiles() -> dict:
    """Load all saved seasonal profiles from disk."""
    profiles = {}
    for f in PROFILES_DIR.glob("*.json"):
        profiles[f.stem] = json.loads(f.read_text())
    return profiles


def save_profile(name: str, data: dict):
    """Save a seasonal profile to disk."""
    filepath = PROFILES_DIR / f"{name}.json"
    filepath.write_text(json.dumps(data, indent=2))


def delete_profile(name: str):
    filepath = PROFILES_DIR / f"{name}.json"
    if filepath.exists():
        filepath.unlink()


def export_current_schedules(tado) -> dict:
    """Read every zone's current schedule and return as a profile dict."""
    zones = tado.get_zones()
    profile = {"exported_at": datetime.now().isoformat(), "zones": {}}

    for zone in zones:
        zid = zone["id"]
        zname = zone["name"]
        try:
            schedule_info = tado.get_schedule(zid)
            timetable_id = schedule_info.get("id", 0)
            blocks = tado.get_schedule_blocks(zid, timetable_id)
            profile["zones"][str(zid)] = {
                "name": zname,
                "timetable_id": timetable_id,
                "blocks": blocks,
            }
        except Exception as e:
            profile["zones"][str(zid)] = {"name": zname, "error": str(e)}

    return profile


def apply_profile(tado, profile: dict):
    """Push a saved profile's schedules to all zones."""
    results = []
    for zid_str, zone_data in profile.get("zones", {}).items():
        zid = int(zid_str)
        zname = zone_data.get("name", f"Zone {zid}")
        if "error" in zone_data or "blocks" not in zone_data:
            results.append((zname, False, "No schedule data in profile"))
            continue
        try:
            tado.set_schedule_blocks(
                zid, zone_data["timetable_id"], zone_data["blocks"]
            )
            results.append((zname, True, "OK"))
        except Exception as e:
            results.append((zname, False, str(e)))
    return results


# ---------------------------------------------------------------------------
# Auth page
# ---------------------------------------------------------------------------


def render_auth_page():
    st.title("🌡️ Tado Control")
    st.markdown("Connect to your Tado account to get started.")

    tab_device, tab_token = st.tabs(["Device Login", "Paste Refresh Token"])

    with tab_device:
        st.markdown(
            "This uses Tado's OAuth2 device code flow. "
            "You'll get a URL to open in your browser to authorise."
        )

        if "auth_flow_started" not in st.session_state:
            st.session_state.auth_flow_started = False

        if not st.session_state.auth_flow_started:
            if st.button("Start Login", type="primary"):
                from libtado.api import Tado

                # Tado() with no token automatically starts the device code flow
                t = Tado()
                st.session_state.auth_tado = t
                st.session_state.auth_url = t.get_device_verification_url()
                st.session_state.auth_user_code = getattr(t, "user_code", None)
                st.session_state.auth_flow_started = True
                st.rerun()
        else:
            url = st.session_state.get("auth_url", "")
            user_code = st.session_state.get("auth_user_code", "")

            st.info(f"**1.** Open this URL in your browser:\n\n{url}")
            if user_code:
                st.success(f"**2.** Enter this code when prompted: **{user_code}**")
            st.markdown("**3.** Log in with your Tado credentials, then click the button below.")

            if st.button("I've logged in, check now"):
                t = st.session_state.auth_tado
                try:
                    activated = t.check_device_activation()
                    if activated:
                        t.device_ready()
                        st.session_state.tado = t
                        _persist_token(t)
                        st.session_state.auth_flow_started = False
                        st.success("Connected!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.warning(
                            "Not yet authorised. Open the URL above and try again."
                        )
                except Exception as e:
                    st.error(f"Auth check failed: {e}")

            if st.button("Cancel"):
                st.session_state.auth_flow_started = False
                st.rerun()

    with tab_token:
        st.markdown(
            "If you already have a refresh token (e.g. from a previous session), "
            "paste it here."
        )
        token = st.text_input("Refresh token", type="password")
        if st.button("Connect with token"):
            if token.strip():
                from libtado.api import Tado

                try:
                    t = Tado(saved_refresh_token=token.strip())
                    status = t.get_device_activation_status()
                    if status.name == "COMPLETED":
                        t.device_ready()
                        st.session_state.tado = t
                        _persist_token(t)
                        st.success("Connected!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Token invalid or expired. Use device login instead.")
                except Exception as e:
                    st.error(f"Failed: {e}")


# ---------------------------------------------------------------------------
# Dashboard page
# ---------------------------------------------------------------------------


def render_dashboard(tado):
    st.title("🌡️ Dashboard")

    try:
        zones = tado.get_zones()
        zone_states = tado.get_zone_states()
        devices = tado.get_devices()
        weather = tado.get_weather()
        home_state = tado.get_home_state()
    except Exception as e:
        st.error(f"Failed to fetch data: {e}")
        if st.button("Re-authenticate"):
            st.session_state.tado = None
            st.rerun()
        return

    # Home status bar
    presence = home_state.get("presence", "UNKNOWN")
    outside_temp = weather.get("outsideTemperature", {}).get("celsius", "?")
    solar = weather.get("solarIntensity", {}).get("percentage", "?")

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Home", presence.title())
    col_b.metric("Outside", f"{outside_temp}°C")
    col_c.metric("Solar Intensity", f"{solar}%")

    st.divider()

    # Build device lookup for battery info
    device_battery = {}
    for d in devices:
        serial = d.get("serialNo", "")
        battery = d.get("batteryState", "UNKNOWN")
        device_battery[serial] = battery

    # Zone cards
    zone_state_map = zone_states.get("zoneStates", zone_states)

    cols_per_row = 3
    zone_list = sorted(zones, key=lambda z: z["id"])

    for i in range(0, len(zone_list), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(zone_list):
                break

            zone = zone_list[idx]
            zid = zone["id"]
            zname = zone["name"]
            state = zone_state_map.get(str(zid), {})

            with col:
                with st.container(border=True):
                    # Current temp
                    sensor = state.get("sensorDataPoints", {})
                    temp = sensor.get("insideTemperature", {}).get("celsius", "?")
                    humidity = sensor.get("humidity", {}).get("percentage", "?")

                    # Target temp
                    setting = state.get("setting", {})
                    target = setting.get("temperature", {})
                    target_temp = target.get("celsius", "off") if target else "off"
                    power = setting.get("power", "OFF")

                    # Heating power percentage
                    activity = state.get("activityDataPoints", {})
                    heating_pct = activity.get("heatingPower", {}).get(
                        "percentage", 0
                    )

                    # Overlay (manual override)?
                    overlay = state.get("overlay")
                    is_manual = overlay is not None

                    # Zone devices for battery
                    zone_devices = [
                        d
                        for d in devices
                        if d.get("currentFwVersion")
                        and any(
                            zd.get("serialNo") == d.get("serialNo")
                            for zd in zone.get("devices", [])
                        )
                    ]
                    battery_states = [
                        device_battery.get(d.get("serialNo", ""), "?")
                        for d in zone.get("devices", [])
                    ]

                    # Display
                    st.markdown(f"**{zname}**")

                    m1, m2 = st.columns(2)
                    m1.metric("Now", f"{temp}°C" if temp != "?" else "?")
                    if power == "ON" and target_temp != "off":
                        m2.metric("Target", f"{target_temp}°C")
                    else:
                        m2.metric("Target", "Off")

                    # Status chips
                    status_parts = []
                    if heating_pct and heating_pct > 0:
                        status_parts.append(f"🔥 {heating_pct}%")
                    if humidity != "?":
                        status_parts.append(f"💧 {humidity}%")
                    if is_manual:
                        status_parts.append("✋ Manual")
                    for bs in battery_states:
                        if bs == "LOW":
                            status_parts.append("🪫 Low battery")
                        elif bs == "NORMAL":
                            status_parts.append("🔋 OK")

                    if status_parts:
                        st.caption(" · ".join(status_parts))


# ---------------------------------------------------------------------------
# Global override page
# ---------------------------------------------------------------------------


def render_global_override(tado):
    st.title("🎛️ Global Override")
    st.markdown("Control all rooms at once.")

    try:
        zones = tado.get_zones()
        home_state = tado.get_home_state()
    except Exception as e:
        st.error(f"Failed to fetch zones: {e}")
        return

    heating_zones = [z for z in zones if z.get("type") == "HEATING"]

    # Home / Away toggle
    st.subheader("Presence")
    presence = home_state.get("presence", "HOME")
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button(
            "🏠 Home", type="primary" if presence == "HOME" else "secondary"
        ):
            tado.set_home_state(True)
            st.success("Set to Home")
            time.sleep(0.5)
            st.rerun()
    with col2:
        if st.button(
            "🚶 Away", type="primary" if presence == "AWAY" else "secondary"
        ):
            tado.set_home_state(False)
            st.success("Set to Away")
            time.sleep(0.5)
            st.rerun()

    st.divider()

    # Global temperature override
    st.subheader("Set all rooms")

    override_temp = st.slider(
        "Temperature (°C)", min_value=5.0, max_value=25.0, value=20.0, step=0.5
    )

    termination = st.radio(
        "Duration",
        ["Until next schedule change", "1 hour", "2 hours", "3 hours", "Manual (until cancelled)"],
        horizontal=True,
    )

    term_map = {
        "Until next schedule change": "NEXT_TIME_BLOCK",
        "1 hour": 3600,
        "2 hours": 7200,
        "3 hours": 10800,
        "Manual (until cancelled)": "MANUAL",
    }
    term_value = term_map[termination]

    col_set, col_resume = st.columns(2)

    with col_set:
        if st.button("Apply to all rooms", type="primary"):
            errors = []
            for zone in heating_zones:
                try:
                    tado.set_temperature(
                        zone["id"], override_temp, termination=term_value
                    )
                except Exception as e:
                    errors.append(f"{zone['name']}: {e}")

            if errors:
                st.error("Some zones failed:\n" + "\n".join(errors))
            else:
                st.success(
                    f"All {len(heating_zones)} rooms set to {override_temp}°C"
                )

    with col_resume:
        if st.button("Resume schedule (all rooms)"):
            errors = []
            for zone in heating_zones:
                try:
                    tado.end_manual_control(zone["id"])
                except Exception as e:
                    errors.append(f"{zone['name']}: {e}")

            if errors:
                st.error("Some zones failed:\n" + "\n".join(errors))
            else:
                st.success("All rooms back on schedule")

    st.divider()

    # Per-room quick overrides
    st.subheader("Per-room quick controls")

    for zone in heating_zones:
        with st.expander(zone["name"]):
            zid = zone["id"]
            c1, c2, c3 = st.columns([2, 1, 1])
            with c1:
                room_temp = st.slider(
                    "Temp",
                    5.0,
                    25.0,
                    20.0,
                    0.5,
                    key=f"room_temp_{zid}",
                )
            with c2:
                if st.button("Set", key=f"set_{zid}"):
                    try:
                        tado.set_temperature(zid, room_temp, termination=term_value)
                        st.success(f"{zone['name']} → {room_temp}°C")
                    except Exception as e:
                        st.error(str(e))
            with c3:
                if st.button("Resume", key=f"resume_{zid}"):
                    try:
                        tado.end_manual_control(zid)
                        st.success(f"{zone['name']} back on schedule")
                    except Exception as e:
                        st.error(str(e))


# ---------------------------------------------------------------------------
# Seasonal profiles page
# ---------------------------------------------------------------------------


def render_profiles(tado):
    st.title("📅 Seasonal Profiles")
    st.markdown(
        "Save your current schedule as a named profile (e.g. 'Winter', 'Summer'). "
        "Switch between them with one click instead of editing room by room."
    )

    profiles = load_profiles()

    # Save current schedule as profile
    st.subheader("Save current schedule")
    new_name = st.text_input(
        "Profile name",
        placeholder="e.g. Winter, Autumn, Holiday",
    )

    if st.button("Save current schedule as profile", type="primary"):
        if not new_name.strip():
            st.warning("Enter a profile name.")
        else:
            with st.spinner("Reading schedules from all zones..."):
                profile_data = export_current_schedules(tado)
            save_profile(new_name.strip(), profile_data)
            st.success(f"Saved '{new_name.strip()}'")
            time.sleep(0.5)
            st.rerun()

    st.divider()

    # Existing profiles
    st.subheader("Saved profiles")

    if not profiles:
        st.info("No profiles saved yet. Set up your schedule in the Tado app, then save it here.")
        return

    for pname, pdata in profiles.items():
        with st.expander(f"📋 {pname}"):
            exported = pdata.get("exported_at", "?")
            zones_data = pdata.get("zones", {})
            zone_count = len(zones_data)
            zones_with_data = sum(
                1 for z in zones_data.values() if "blocks" in z
            )

            st.caption(f"Saved: {exported} · {zones_with_data}/{zone_count} zones with schedule data")

            # Show summary of temperatures per zone
            for zid, zinfo in zones_data.items():
                zname = zinfo.get("name", f"Zone {zid}")
                blocks = zinfo.get("blocks", [])
                if blocks:
                    temps = set()
                    for block in blocks:
                        t = block.get("setting", {}).get("temperature", {})
                        if t:
                            temps.add(t.get("celsius", "?"))
                    temp_str = ", ".join(f"{t}°C" for t in sorted(temps) if t != "?")
                    st.caption(f"  {zname}: {temp_str if temp_str else 'off'}")

            col_apply, col_delete = st.columns(2)
            with col_apply:
                if st.button(f"Apply '{pname}'", key=f"apply_{pname}", type="primary"):
                    with st.spinner(f"Applying '{pname}' to all zones..."):
                        results = apply_profile(tado, pdata)

                    for zname, success, msg in results:
                        if success:
                            st.success(f"{zname}: applied")
                        else:
                            st.error(f"{zname}: {msg}")

            with col_delete:
                if st.button(f"Delete '{pname}'", key=f"delete_{pname}"):
                    delete_profile(pname)
                    st.rerun()


# ---------------------------------------------------------------------------
# Devices & offsets page
# ---------------------------------------------------------------------------


def render_devices(tado):
    st.title("🔧 Devices & Offsets")

    try:
        zones = tado.get_zones()
        devices = tado.get_devices()
    except Exception as e:
        st.error(f"Failed to fetch devices: {e}")
        return

    # Build zone-to-device mapping
    zone_device_map = {}
    for zone in zones:
        for zd in zone.get("devices", []):
            zone_device_map[zd.get("serialNo")] = zone["name"]

    st.subheader("Device status")

    for device in devices:
        serial = device.get("serialNo", "?")
        dev_type = device.get("deviceType", "?")
        battery = device.get("batteryState", "N/A")
        fw = device.get("currentFwVersion", "?")
        connection = device.get("connectionState", {}).get("value", "?")
        zone_name = zone_device_map.get(serial, "Unassigned")

        with st.container(border=True):
            c1, c2, c3, c4 = st.columns(4)
            c1.markdown(f"**{zone_name}**")
            c2.caption(f"{dev_type}")

            if battery == "LOW":
                c3.warning("🪫 Low battery")
            elif battery == "NORMAL":
                c3.success("🔋 OK")
            else:
                c3.caption(f"Battery: {battery}")

            if connection == "true" or connection is True:
                c4.success("Connected")
            else:
                c4.error("Offline")

            # Temperature offset
            if "SRT" in dev_type or "RU" in dev_type or "VA" in dev_type:
                try:
                    offset_data = tado.get_temperature_offset(serial)
                    current_offset = offset_data.get("celsius", 0)
                except Exception:
                    current_offset = 0

                new_offset = st.slider(
                    f"Temperature offset for {zone_name} ({serial})",
                    min_value=-5.0,
                    max_value=5.0,
                    value=float(current_offset),
                    step=0.1,
                    key=f"offset_{serial}",
                    help="Positive = device reads warmer than reality. "
                    "Set negative to compensate for radiator heat.",
                )

                if st.button(f"Update offset", key=f"set_offset_{serial}"):
                    try:
                        tado.set_temperature_offset(serial, new_offset)
                        st.success(
                            f"Offset for {zone_name} set to {new_offset}°C"
                        )
                    except Exception as e:
                        st.error(f"Failed: {e}")


# ---------------------------------------------------------------------------
# Sidebar navigation & settings
# ---------------------------------------------------------------------------

tado = _get_tado_client()

if tado is None:
    render_auth_page()
else:
    # Sidebar
    with st.sidebar:
        st.title("Tado Control")

        page = st.radio(
            "Navigate",
            ["Dashboard", "Global Override", "Seasonal Profiles", "Devices & Offsets"],
            label_visibility="collapsed",
        )

        st.divider()

        # Show refresh token for user to copy (useful for Streamlit Cloud secrets)
        with st.expander("Connection"):
            try:
                me = tado.get_me()
                name = me.get("name", "?")
                email = me.get("email", "?")
                st.caption(f"Logged in as **{name}** ({email})")
            except Exception:
                st.caption("Connected")

            if hasattr(tado, "refresh_token") and tado.refresh_token:
                st.text_input(
                    "Refresh token (save this for next time)",
                    value=tado.refresh_token,
                    type="password",
                    key="show_refresh_token",
                )

            if st.button("Disconnect"):
                st.session_state.tado = None
                if TOKEN_FILE.exists():
                    TOKEN_FILE.unlink()
                st.rerun()

        st.divider()
        st.caption("Auto-refreshes when you interact. Pull down to refresh on mobile.")

    # Render selected page
    if page == "Dashboard":
        render_dashboard(tado)
    elif page == "Global Override":
        render_global_override(tado)
    elif page == "Seasonal Profiles":
        render_profiles(tado)
    elif page == "Devices & Offsets":
        render_devices(tado)
