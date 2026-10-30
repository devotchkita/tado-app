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
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Custom CSS – match the artifact's design language
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');

/* Hide Streamlit chrome */
#MainMenu, header, footer { visibility: hidden; }
.block-container { padding-top: 1rem; max-width: 520px; }

/* Override Streamlit font */
html, body, [class*="css"] {
    font-family: 'DM Sans', -apple-system, sans-serif;
}

/* Room card grid */
.room-grid {
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin: 8px 0;
}

.room-card {
    background: var(--secondary-background-color, #F5F5F5);
    border: 1.5px solid rgba(128,128,128,0.15);
    border-radius: 12px;
    padding: 14px 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.room-card.heating {
    border-color: #E8553A;
    border-left: 4px solid #E8553A;
}

.room-card.off {
    opacity: 0.5;
}

.room-left {
    display: flex;
    align-items: center;
    gap: 12px;
}

.room-icon {
    font-size: 20px;
    width: 36px;
    height: 36px;
    border-radius: 8px;
    background: rgba(128,128,128,0.08);
    display: flex;
    align-items: center;
    justify-content: center;
}

.room-name {
    font-size: 14px;
    font-weight: 500;
}

.room-status {
    font-size: 11px;
    color: #6B6B6B;
    margin-top: 1px;
}

.room-right {
    text-align: right;
}

.room-temp {
    font-size: 20px;
    font-weight: 600;
    font-family: 'DM Mono', monospace;
}

.room-target {
    font-size: 11px;
    color: #6B6B6B;
}

/* Global thermostat display */
.global-display {
    text-align: center;
    padding: 24px 0 16px;
}

.global-temp {
    font-size: 56px;
    font-weight: 700;
    font-family: 'DM Mono', monospace;
    letter-spacing: -2px;
    line-height: 1;
}

.global-temp .unit {
    font-size: 22px;
    font-weight: 400;
    color: #6B6B6B;
    vertical-align: super;
}

.global-label {
    font-size: 13px;
    color: #6B6B6B;
    margin-top: 6px;
}

/* Stat row */
.stat-row {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 8px;
    margin: 12px 0;
}

.stat-card {
    background: var(--secondary-background-color, #F5F5F5);
    border-radius: 10px;
    padding: 12px;
    text-align: center;
}

.stat-value {
    font-size: 18px;
    font-weight: 600;
    font-family: 'DM Mono', monospace;
}

.stat-label {
    font-size: 11px;
    color: #6B6B6B;
    margin-top: 2px;
}

/* Section headers */
.section-label {
    font-size: 13px;
    font-weight: 600;
    color: #6B6B6B;
    margin: 20px 0 8px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Battery badges */
.battery-low {
    display: inline-block;
    background: #FEF2F0;
    color: #E8553A;
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
    border-radius: 4px;
}

/* Profile card */
.profile-card {
    background: var(--secondary-background-color, #F5F5F5);
    border: 1.5px solid rgba(128,128,128,0.15);
    border-radius: 10px;
    padding: 14px;
    margin: 6px 0;
}

.profile-name {
    font-size: 15px;
    font-weight: 600;
}

.profile-meta {
    font-size: 11px;
    color: #6B6B6B;
    margin-top: 2px;
}

/* Override streamlit button styling */
.stButton > button {
    border-radius: 10px;
    font-family: 'DM Sans', sans-serif;
    font-weight: 500;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROFILES_DIR = Path(__file__).parent / "profiles"
PROFILES_DIR.mkdir(exist_ok=True)
TOKEN_FILE = Path(__file__).parent / ".tado_token.json"

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_tado_client():
    from libtado.api import Tado

    if "tado" in st.session_state and st.session_state.tado is not None:
        try:
            st.session_state.tado.refresh_auth()
            return st.session_state.tado
        except Exception:
            st.session_state.tado = None

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
    try:
        token_data = {
            "refresh_token": tado_client.refresh_token,
            "saved_at": datetime.now().isoformat(),
        }
        TOKEN_FILE.write_text(json.dumps(token_data, indent=2))
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------


def load_profiles() -> dict:
    profiles = {}
    for f in PROFILES_DIR.glob("*.json"):
        profiles[f.stem] = json.loads(f.read_text())
    return profiles


def save_profile(name: str, data: dict):
    filepath = PROFILES_DIR / f"{name}.json"
    filepath.write_text(json.dumps(data, indent=2))


def delete_profile(name: str):
    filepath = PROFILES_DIR / f"{name}.json"
    if filepath.exists():
        filepath.unlink()


def export_current_schedules(tado) -> dict:
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
# Data fetching (cached briefly)
# ---------------------------------------------------------------------------


def fetch_all_data(tado):
    """Fetch all zone data in one go. Returns dict."""
    try:
        zones = tado.get_zones()
        zone_states = tado.get_zone_states()
        devices = tado.get_devices()
        weather = tado.get_weather()
        home_state = tado.get_home_state()
        return {
            "zones": zones,
            "zone_states": zone_states.get("zoneStates", zone_states),
            "devices": devices,
            "weather": weather,
            "home_state": home_state,
        }
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Room icon mapping
# ---------------------------------------------------------------------------
ROOM_ICONS = {
    "living": "🛋", "lounge": "🛋", "sitting": "🛋",
    "bedroom": "🛏", "bed": "🛏", "master": "🛏", "guest": "🛏",
    "kitchen": "🍳", "dining": "🍽",
    "office": "💻", "study": "💻", "work": "💻",
    "bathroom": "🚿", "bath": "🚿", "shower": "🚿", "ensuite": "🚿",
    "hallway": "🚪", "hall": "🚪", "landing": "🚪", "corridor": "🚪",
    "nursery": "🧸", "playroom": "🧸", "kid": "🧸", "child": "🧸",
    "garage": "🔧", "utility": "🔧", "laundry": "🧺",
}


def get_room_icon(name):
    name_lower = name.lower()
    for key, icon in ROOM_ICONS.items():
        if key in name_lower:
            return icon
    return "🌡"


# ---------------------------------------------------------------------------
# Auth page
# ---------------------------------------------------------------------------


def render_auth_page():
    st.markdown('<div class="global-display"><div class="global-temp">🌡️</div>'
                '<div class="global-label">Tado Control</div></div>',
                unsafe_allow_html=True)
    st.markdown("Connect to your Tado account to get started.")

    tab_device, tab_token = st.tabs(["Device Login", "Paste Refresh Token"])

    with tab_device:
        st.markdown(
            "Uses Tado's OAuth2 device code flow. "
            "You'll get a URL and code to enter in your browser."
        )

        if "auth_flow_started" not in st.session_state:
            st.session_state.auth_flow_started = False

        if not st.session_state.auth_flow_started:
            if st.button("Start Login", type="primary", use_container_width=True):
                from libtado.api import Tado
                t = Tado()
                st.session_state.auth_tado = t
                st.session_state.auth_url = t.get_device_verification_url()
                st.session_state.auth_user_code = getattr(t, "user_code", None)
                st.session_state.auth_flow_started = True
                st.rerun()
        else:
            url = st.session_state.get("auth_url", "")
            user_code = st.session_state.get("auth_user_code", "")

            st.info(f"**1.** Open this URL:\n\n{url}")
            if user_code:
                st.success(f"**2.** Enter this code: **{user_code}**")
            st.markdown("**3.** Log in, then click below.")

            c1, c2 = st.columns(2)
            with c1:
                if st.button("I've logged in ✓", type="primary", use_container_width=True):
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
                            st.warning("Not yet authorised. Try again.")
                    except Exception as e:
                        st.error(f"Auth check failed: {e}")
            with c2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state.auth_flow_started = False
                    st.rerun()

    with tab_token:
        st.markdown("Paste a refresh token from a previous session.")
        token = st.text_input("Refresh token", type="password")
        if st.button("Connect", use_container_width=True):
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
                        st.error("Token invalid or expired.")
                except Exception as e:
                    st.error(f"Failed: {e}")


# ---------------------------------------------------------------------------
# Main dashboard
# ---------------------------------------------------------------------------


def render_main(tado):
    data = fetch_all_data(tado)

    if "error" in data:
        st.error(f"Failed to fetch data: {data['error']}")
        if st.button("Re-authenticate"):
            st.session_state.tado = None
            st.rerun()
        return

    zones = data["zones"]
    zone_states = data["zone_states"]
    weather = data["weather"]
    home_state = data["home_state"]
    devices = data["devices"]

    heating_zones = [z for z in zones if z.get("type") == "HEATING"]

    # Build per-zone state info
    room_data = []
    for zone in sorted(heating_zones, key=lambda z: z["id"]):
        zid = zone["id"]
        state = zone_states.get(str(zid), {})
        sensor = state.get("sensorDataPoints", {})
        setting = state.get("setting", {})
        activity = state.get("activityDataPoints", {})
        overlay = state.get("overlay")

        current = sensor.get("insideTemperature", {}).get("celsius")
        humidity = sensor.get("humidity", {}).get("percentage")
        power = setting.get("power", "OFF")
        target_obj = setting.get("temperature", {})
        target = target_obj.get("celsius") if target_obj else None
        heating_pct = activity.get("heatingPower", {}).get("percentage", 0)
        is_manual = overlay is not None

        # Battery from devices
        zone_device_serials = [d.get("serialNo") for d in zone.get("devices", [])]
        battery_states = []
        for d in devices:
            if d.get("serialNo") in zone_device_serials:
                battery_states.append(d.get("batteryState", "UNKNOWN"))

        # Status text
        if power == "OFF" or target is None:
            status_text = "Off"
        elif heating_pct and heating_pct > 0:
            status_text = f"Heating · {heating_pct}%"
        elif is_manual:
            status_text = "Manual"
        else:
            status_text = "Idle"

        room_data.append({
            "id": zid,
            "name": zone["name"],
            "icon": get_room_icon(zone["name"]),
            "current": current,
            "target": target,
            "power": power,
            "humidity": humidity,
            "heating_pct": heating_pct or 0,
            "status": status_text,
            "is_manual": is_manual,
            "battery_low": "LOW" in battery_states,
        })

    # --- Navigation tabs ---
    tab_home, tab_profiles, tab_devices = st.tabs(["🌡 Home", "📅 Profiles", "🔧 Devices"])

    # ==================================================================
    # HOME TAB
    # ==================================================================
    with tab_home:
        # Header row
        presence = home_state.get("presence", "UNKNOWN")
        outside = weather.get("outsideTemperature", {}).get("celsius", "?")

        st.markdown(
            f'<div class="stat-row">'
            f'<div class="stat-card"><div class="stat-value">{presence.title()}</div>'
            f'<div class="stat-label">Presence</div></div>'
            f'<div class="stat-card"><div class="stat-value">{outside}°</div>'
            f'<div class="stat-label">Outside</div></div>'
            f'<div class="stat-card"><div class="stat-value">{len(room_data)}</div>'
            f'<div class="stat-label">Zones</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # --- GLOBAL CONTROL ---
        st.markdown('<div class="section-label">Global control</div>', unsafe_allow_html=True)

        # Init session state for global temp
        if "global_target" not in st.session_state:
            # Default to median of current targets
            active_targets = [r["target"] for r in room_data if r["target"] is not None]
            st.session_state.global_target = (
                round(sum(active_targets) / len(active_targets) * 2) / 2
                if active_targets else 20.0
            )

        # Temperature display + controls
        gt = st.session_state.global_target
        st.markdown(
            f'<div class="global-display">'
            f'<div class="global-temp">{gt:.1f}<span class="unit">°C</span></div>'
            f'<div class="global-label">Target for all rooms</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        c_down, c_slider, c_up = st.columns([1, 4, 1])
        with c_down:
            if st.button("−", key="temp_down", use_container_width=True):
                st.session_state.global_target = max(5.0, gt - 0.5)
                st.rerun()
        with c_slider:
            new_temp = st.slider(
                "Global target",
                5.0, 25.0, gt, 0.5,
                label_visibility="collapsed",
            )
            if new_temp != gt:
                st.session_state.global_target = new_temp
                st.rerun()
        with c_up:
            if st.button("+", key="temp_up", use_container_width=True):
                st.session_state.global_target = min(25.0, gt + 0.5)
                st.rerun()

        # Duration selector
        duration = st.radio(
            "Duration",
            ["Until next block", "1 hour", "2 hours", "Manual"],
            horizontal=True,
            label_visibility="collapsed",
        )
        term_map = {
            "Until next block": "AUTO",
            "1 hour": 3600,
            "2 hours": 7200,
            "Manual": "MANUAL",
        }

        c_apply, c_resume = st.columns(2)
        with c_apply:
            if st.button("🔥 Apply to all rooms", type="primary", use_container_width=True):
                errors = []
                for room in room_data:
                    try:
                        tado.set_temperature(
                            room["id"],
                            st.session_state.global_target,
                            termination=term_map[duration],
                        )
                    except Exception as e:
                        errors.append(f"{room['name']}: {e}")
                if errors:
                    st.error("\n".join(errors))
                else:
                    st.success(f"All {len(room_data)} rooms → {st.session_state.global_target}°C")
                    time.sleep(1)
                    st.rerun()

        with c_resume:
            if st.button("⏹ Resume all schedules", use_container_width=True):
                errors = []
                for room in room_data:
                    try:
                        tado.end_manual_control(room["id"])
                    except Exception as e:
                        errors.append(f"{room['name']}: {e}")
                if errors:
                    st.error("\n".join(errors))
                else:
                    st.success("All rooms back on schedule")
                    time.sleep(1)
                    st.rerun()

        # --- ROOM CARDS ---
        st.markdown('<div class="section-label">Rooms</div>', unsafe_allow_html=True)

        # Render room cards as HTML for the display, Streamlit buttons for actions
        for room in room_data:
            is_heating = room["heating_pct"] > 0
            is_off = room["power"] == "OFF" or room["target"] is None
            card_class = "heating" if is_heating else ("off" if is_off else "")

            battery_badge = ' <span class="battery-low">LOW BATTERY</span>' if room["battery_low"] else ""

            target_display = f"{room['target']}°" if room["target"] else "Off"
            current_display = f"{room['current']:.1f}°" if room["current"] else "?"
            humidity_display = f" · 💧{room['humidity']}%" if room.get("humidity") else ""

            st.markdown(
                f'<div class="room-card {card_class}">'
                f'  <div class="room-left">'
                f'    <div class="room-icon">{room["icon"]}</div>'
                f'    <div>'
                f'      <div class="room-name">{room["name"]}{battery_badge}</div>'
                f'      <div class="room-status">{room["status"]}{humidity_display}</div>'
                f'    </div>'
                f'  </div>'
                f'  <div class="room-right">'
                f'    <div class="room-temp">{current_display}</div>'
                f'    <div class="room-target">Target {target_display}</div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Per-room quick controls in an expander
            with st.expander(f"Control {room['name']}", expanded=False):
                rc1, rc2, rc3 = st.columns([3, 1, 1])
                with rc1:
                    room_temp = st.slider(
                        "Temp",
                        5.0, 25.0,
                        float(room["target"]) if room["target"] else 20.0,
                        0.5,
                        key=f"rt_{room['id']}",
                        label_visibility="collapsed",
                    )
                with rc2:
                    if st.button("Set", key=f"set_{room['id']}", use_container_width=True):
                        try:
                            tado.set_temperature(room["id"], room_temp, termination=term_map[duration])
                            st.success(f"→ {room_temp}°C")
                            time.sleep(0.5)
                            st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with rc3:
                    if is_off:
                        if st.button("On", key=f"on_{room['id']}", use_container_width=True):
                            try:
                                tado.end_manual_control(room["id"])
                                st.success("Resumed schedule")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))
                    else:
                        if st.button("Off", key=f"off_{room['id']}", use_container_width=True):
                            try:
                                tado.set_temperature(room["id"], 5.0, termination="MANUAL")
                                st.success("Turned off")
                                time.sleep(0.5)
                                st.rerun()
                            except Exception as e:
                                st.error(str(e))

    # ==================================================================
    # PROFILES TAB
    # ==================================================================
    with tab_profiles:
        st.markdown('<div class="section-label">Save current schedule</div>', unsafe_allow_html=True)

        new_name = st.text_input("Profile name", placeholder="e.g. Winter, Summer, Holiday")
        if st.button("Save current schedule as profile", type="primary", use_container_width=True):
            if not new_name.strip():
                st.warning("Enter a name.")
            else:
                with st.spinner("Reading schedules..."):
                    profile_data = export_current_schedules(tado)
                save_profile(new_name.strip(), profile_data)
                st.success(f"Saved '{new_name.strip()}'")
                time.sleep(0.5)
                st.rerun()

        profiles = load_profiles()
        if profiles:
            st.markdown('<div class="section-label">Saved profiles</div>', unsafe_allow_html=True)
            for pname, pdata in profiles.items():
                zones_data = pdata.get("zones", {})
                zone_count = len(zones_data)
                zones_ok = sum(1 for z in zones_data.values() if "blocks" in z)
                exported = pdata.get("exported_at", "?")[:10]

                st.markdown(
                    f'<div class="profile-card">'
                    f'<div class="profile-name">📋 {pname}</div>'
                    f'<div class="profile-meta">Saved {exported} · {zones_ok}/{zone_count} zones</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                c_a, c_d = st.columns(2)
                with c_a:
                    if st.button(f"Apply '{pname}'", key=f"apply_{pname}", type="primary", use_container_width=True):
                        with st.spinner(f"Applying '{pname}'..."):
                            results = apply_profile(tado, pdata)
                        for zname, success, msg in results:
                            if success:
                                st.success(f"{zname} ✓")
                            else:
                                st.error(f"{zname}: {msg}")
                with c_d:
                    if st.button(f"Delete", key=f"del_{pname}", use_container_width=True):
                        delete_profile(pname)
                        st.rerun()
        else:
            st.info("No profiles yet. Set up your schedule in the Tado app, then save it here.")

    # ==================================================================
    # DEVICES TAB
    # ==================================================================
    with tab_devices:
        st.markdown('<div class="section-label">Devices</div>', unsafe_allow_html=True)

        zone_device_map = {}
        for zone in zones:
            for zd in zone.get("devices", []):
                zone_device_map[zd.get("serialNo")] = zone["name"]

        for device in devices:
            serial = device.get("serialNo", "?")
            dev_type = device.get("deviceType", "?")
            battery = device.get("batteryState", "N/A")
            connection = device.get("connectionState", {}).get("value", False)
            zone_name = zone_device_map.get(serial, "Unassigned")

            conn_icon = "🟢" if connection else "🔴"
            batt_text = "🪫 LOW" if battery == "LOW" else ("🔋" if battery == "NORMAL" else battery)

            st.markdown(
                f'<div class="room-card">'
                f'  <div class="room-left">'
                f'    <div class="room-icon">{conn_icon}</div>'
                f'    <div>'
                f'      <div class="room-name">{zone_name}</div>'
                f'      <div class="room-status">{dev_type} · {batt_text}</div>'
                f'    </div>'
                f'  </div>'
                f'  <div class="room-right">'
                f'    <div class="room-target">{serial}</div>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Offset controls for radiator valves
            if any(t in dev_type for t in ["SRT", "RU", "VA"]):
                try:
                    offset_data = tado.get_temperature_offset(serial)
                    current_offset = offset_data.get("celsius", 0)
                except Exception:
                    current_offset = 0

                new_offset = st.slider(
                    f"Offset ({zone_name})",
                    -5.0, 5.0, float(current_offset), 0.1,
                    key=f"off_{serial}",
                )
                if st.button(f"Update offset", key=f"setoff_{serial}"):
                    try:
                        tado.set_temperature_offset(serial, new_offset)
                        st.success(f"{zone_name} offset → {new_offset}°C")
                    except Exception as e:
                        st.error(str(e))


# ---------------------------------------------------------------------------
# Sidebar – connection info
# ---------------------------------------------------------------------------

tado = _get_tado_client()

if tado is not None:
    with st.sidebar:
        st.markdown("**Connection**")
        try:
            me = tado.get_me()
            st.caption(f"Logged in as {me.get('name', '?')}")
        except Exception:
            st.caption("Connected")

        if hasattr(tado, "refresh_token") and tado.refresh_token:
            st.text_input(
                "Refresh token (save for next time)",
                value=tado.refresh_token,
                type="password",
                key="show_token",
            )

        if st.button("Disconnect"):
            st.session_state.tado = None
            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            st.rerun()

# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

if tado is None:
    render_auth_page()
else:
    render_main(tado)
