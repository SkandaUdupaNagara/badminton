import streamlit as st
import time
import datetime
from datetime import timezone, timedelta
import pandas as pd
import random
import string
import json
from typing import List, Dict, Any, Optional

# --- Firebase Imports ---
import firebase_admin
from firebase_admin import credentials, firestore
from streamlit_autorefresh import st_autorefresh

# --- Cookie Manager Import ---
import extra_streamlit_components as stx

# ────────────────────────────────────────────────────────────────────────────────
# CONFIGURATION & INITIAL DATA
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Acers Badminton Club 2025", layout="wide", initial_sidebar_state="expanded")

# --- Constants & Secrets ---
MAX_COURTS = 4
SKILL_MAP = {1: 'Beginner', 2: 'Intermediate', 3: 'Advanced'}

try:
    ADMIN_PASSWORD = st.secrets.app_secrets.admin_password
    ADMIN_USERS = st.secrets.app_secrets.admin_users
except AttributeError:
    st.error("Your `secrets.toml` file is missing or misconfigured.")
    st.stop()


# --- Custom CSS ---
st.markdown("""<style>...</style>""", unsafe_allow_html=True) # CSS hidden for brevity

# --- Firebase Integration ---
def init_firebase():
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(dict(st.secrets["firebase_credentials"]))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}"); return None

db = init_firebase()

STATE_DOC_REF = db.collection("session").document("live_state") if db else None
PLAYERS_COLLECTION_REF = db.collection("session").document("live_state").collection("players") if db else None
LOG_COLLECTION_REF = db.collection("session").document("live_state").collection("game_log") if db else None

@st.cache_data(ttl=30)
def get_players_db():
    if not PLAYERS_COLLECTION_REF: return {}
    docs = PLAYERS_COLLECTION_REF.stream()
    return {doc.id: doc.to_dict() for doc in docs}

def get_live_state():
    if not STATE_DOC_REF: return {}
    doc = STATE_DOC_REF.get()
    if doc.exists:
        state = doc.to_dict()
        if 'finishers_queue' not in state: state['finishers_queue'] = []
        if 'main_queue' not in state: state['main_queue'] = []
        return state
    else: 
        default_state = {
            'attendees': [], 'finishers_queue': [], 'main_queue': [], 'active_games': {},
            'session_password': generate_password(), 'last_chooser_id': None
        }
        STATE_DOC_REF.set(default_state)
        # Clear player collection as well for a truly fresh start
        for doc in PLAYERS_COLLECTION_REF.stream(): doc.reference.delete()
        return default_state

def generate_password(): return "".join(random.choices(string.digits, k=6))

def get_cookie_manager():
    return stx.CookieManager()

# ────────────────────────────────────────────────────────────────────────────────
# PLAYER & COURT MODES
# ────────────────────────────────────────────────────────────────────────────────
def render_player_mode(live_state, players_db, cookie_manager):
    if 'player_logged_in_name' not in st.session_state: st.session_state.player_logged_in_name = None
    if not st.session_state.player_logged_in_name:
        st.title("🏸 Player Attendance")
        st.write("Log in with your **Name** to mark your attendance.")
        with st.form("player_login_form"):
            typed_name = st.text_input("Enter your name")
            session_password = st.text_input("Today's Session Password", type="password")
            submitted = st.form_submit_button("Mark Attendance")
            if submitted:
                if not typed_name:
                    st.error("Please enter your name.")
                elif session_password != live_state.get('session_password'):
                    st.error("Incorrect session password.")
                else:
                    standardized_name = typed_name.strip().title()
                    found_player = next((p for p in players_db.values() if p.get('name', '').lower() == standardized_name.lower()), None)
                    
                    if not found_player:
                        with st.spinner(f"Adding {standardized_name} to the session..."):
                            new_player_id = int(time.time() * 1000)
                            new_player = {'id': new_player_id, 'name': standardized_name, 'gender': "Men", 'skill': 2, 'chooser_count': 0}
                            PLAYERS_COLLECTION_REF.document(str(new_player_id)).set(new_player)
                            STATE_DOC_REF.update({'attendees': firestore.ArrayUnion([new_player_id]),'main_queue': firestore.ArrayUnion([new_player_id])})
                            found_player = new_player
                            st.cache_data.clear()
                    
                    st.session_state.player_logged_in_name = found_player['name']
                    cookie_manager.set('player_name', found_player['name'], expires_at=datetime.datetime.now() + timedelta(hours=3))
                    player_id = found_player['id']
                    if player_id not in live_state.get('attendees', []):
                        STATE_DOC_REF.update({'attendees': firestore.ArrayUnion([player_id]), 'main_queue': firestore.ArrayUnion([player_id])})
                    st.toast(f"Welcome, {found_player['name']}! You're checked in.", icon="✅")
                    st.rerun()
    else:
        st.title(f"✅ Attendance Marked, {st.session_state.player_logged_in_name}!")
        st.subheader("Current Waiting Queue")
        waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
        waiting_players = get_players_from_ids(waiting_pids, players_db)
        if not waiting_players: st.info("The waiting list is empty.")
        else:
            pills = [f"<div class='player-pill' style='{'background-color: #d0eaff; border: 2px solid #006aff;' if p and p['name'] == st.session_state.player_logged_in_name else ''}'>{i+1}. {p['name'] if p else '...'}</div>" for i, p in enumerate(waiting_players)]
            st.markdown("".join(pills), unsafe_allow_html=True)
        if st.button("Logout"):
            st.session_state.logout_in_progress = True
            st.session_state.player_logged_in_name = None
            cookie_manager.delete('player_name')
            st.rerun()
        st_autorefresh(interval=10000, key="player_refresher")

def render_court_mode(live_state, players_db, cookie_manager):
    if 'court_operator_logged_in' not in st.session_state: st.session_state.court_operator_logged_in = None
    if not st.session_state.court_operator_logged_in:
        st.title("🔑 Court Controller Login")
        with st.form("court_login_form"):
            present_pids = live_state.get('attendees', []); present_players = get_players_from_ids(present_pids, players_db)
            present_names = sorted([p['name'] for p in present_players if p]); no_players = not present_names
            if no_players: st.warning("No players have checked in yet.")
            selected_user = st.selectbox("Select your name", present_names, disabled=no_players)
            password = st.text_input("Session Password", type="password", disabled=no_players)
            submitted = st.form_submit_button("Login", disabled=no_players)
            if submitted and not no_players:
                if password == live_state.get('session_password'):
                    st.session_state.court_operator_logged_in = selected_user
                    cookie_manager.set('court_operator', selected_user, expires_at=datetime.datetime.now() + timedelta(hours=3))
                    st.rerun()
                else: st.error("Incorrect password.")
        st.markdown("---")
        with st.expander("Admin Tools"):
            admin_pw = st.text_input("Enter Admin Password", type="password", key="court_admin_pw_check")
            c1, c2 = st.columns(2)
            if c1.button("Show Session Password"):
                if admin_pw == ADMIN_PASSWORD: st.success(f"Password is: **{live_state.get('session_password')}**")
                else: st.error("Incorrect Admin Password.")
            if c2.button("⚙️ Sync Player Roster"):
                if admin_pw == ADMIN_PASSWORD:
                    st.error("Roster is now dynamic. This button is deprecated.")
                else: st.error("Incorrect Admin Password.")
        return
    render_sidebar(live_state, players_db, cookie_manager)
    render_main_dashboard(live_state, players_db)
    st_autorefresh(interval=5000, key="court_refresher")

# --- Helper functions ---
def get_players_from_ids(pids: List[int], players_db: dict) -> List[dict]:
    return [players_db.get(str(pid)) for pid in pids if str(pid) in players_db]

def clear_game_log():
    if LOG_COLLECTION_REF:
        for doc in LOG_COLLECTION_REF.stream(): doc.reference.delete()

# ────────────────────────────────────────────────────────────────────────────────
# UI RENDERING FOR COURT MODE
# ────────────────────────────────────────────────────────────────────────────────
def render_sidebar(live_state, players_db, cookie_manager):
    with st.sidebar:
        st.title("🏸 Acers Badminton Club")
        st.markdown(f"Operator: **{st.session_state.court_operator_logged_in}**")
        if st.button("Logout Operator", use_container_width=True):
            st.session_state.logout_in_progress = True
            st.session_state.court_operator_logged_in = None
            cookie_manager.delete('court_operator')
            st.rerun()
        st.markdown("---")
        all_waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
        attendees, waiting = len(live_state.get('attendees', [])), len(all_waiting_pids)
        on_court = sum(len(g.get('player_ids', [])) for g in live_state.get('active_games', {}).values())
        c1, c2, c3 = st.columns(3); c1.metric("Present", attendees); c2.metric("Waiting", waiting); c3.metric("On Court", on_court)
        st.markdown("---")
        if st.session_state.court_operator_logged_in in ADMIN_USERS:
            st.header("Admin Controls")
            if st.button("🔄 Reset Full Session", use_container_width=True, type="secondary"):
                # --- FIX: Also delete all player documents for a true reset ---
                for doc in PLAYERS_COLLECTION_REF.stream(): doc.reference.delete()
                clear_game_log()
                STATE_DOC_REF.set({'attendees': [], 'finishers_queue': [], 'main_queue': [], 'active_games': {}, 'session_password': generate_password(), 'last_chooser_id': None})
                st.cache_data.clear(); st.rerun()
            if st.button("🔥 Clear Game Log", use_container_width=True, help="Deletes all game log entries."):
                clear_game_log(); st.toast("Game log cleared!", icon="🧹"); st.rerun()

def render_main_dashboard(live_state, players_db):
    courts_col, queue_col = st.columns([3, 1])
    with courts_col:
        tab_dashboard, tab_checkout, tab_log = st.tabs(["🏟️ Courts", "👋 Check-out", "📊 Game Log"])
        with tab_dashboard:
            #...(implementation from previous version)...
        with tab_checkout:
            st.subheader("Player Check-out")
            present_pids = live_state.get('attendees', [])
            present_players = get_players_from_ids(present_pids, players_db)
            if not present_players:
                st.info("No players are currently checked in.")
            else:
                names_to_check_out = st.multiselect("Select players to check out", [p['name'] for p in present_players if p])
                if st.button("Check Out Selected Players", disabled=not names_to_check_out):
                    pids_to_remove = [p['id'] for p in present_players if p and p['name'] in names_to_check_out]
                    STATE_DOC_REF.update({'attendees': firestore.ArrayRemove(pids_to_remove), 'finishers_queue': firestore.ArrayRemove(pids_to_remove), 'main_queue': firestore.ArrayRemove(pids_to_remove)})
                    # Note: We don't delete the player document, just remove them from the session
                    st.toast(f"Checked out {', '.join(names_to_check_out)}.", icon="👋"); st.rerun()
        with tab_log:
            #...(implementation from previous version)...

    with queue_col:
        st.subheader("⏳ Waiting Queue")
        #...(implementation from previous version)...
        if st.session_state.court_operator_logged_in in ADMIN_USERS:
            with st.expander("👑 Remove Player from Queue"):
                waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
                waiting_players = get_players_from_ids(waiting_pids, players_db)
                if not waiting_players:
                    st.write("Queue is empty.")
                else:
                    names_to_remove = st.multiselect("Select players to remove", [p['name'] for p in waiting_players if p])
                    if st.button("Remove Selected Players", disabled=not names_to_remove):
                        pids_to_remove = [p['id'] for p in waiting_players if p and p['name'] in names_to_remove]
                        STATE_DOC_REF.update({'attendees': firestore.ArrayRemove(pids_to_remove), 'finishers_queue': firestore.ArrayRemove(pids_to_remove), 'main_queue': firestore.ArrayRemove(pids_to_remove)})
                        st.toast(f"Removed {', '.join(names_to_remove)}.", icon="👋"); st.rerun()

# ────────────────────────────────────────────────────────────────────────────────
# MAIN APP EXECUTION
# ────────────────────────────────────────────────────────────────────────────────
if not db:
    st.error("Could not connect to Firebase.")
else:
    if 'court_operator_logged_in' not in st.session_state: st.session_state.court_operator_logged_in = None
    if 'player_logged_in_name' not in st.session_state: st.session_state.player_logged_in_name = None
    if 'logout_in_progress' not in st.session_state: st.session_state.logout_in_progress = False
    
    cookie_manager = get_cookie_manager()
    if not st.session_state.court_operator_logged_in and not st.session_state.logout_in_progress:
        st.session_state.court_operator_logged_in = cookie_manager.get('court_operator')
    if not st.session_state.player_logged_in_name and not st.session_state.logout_in_progress:
        st.session_state.player_logged_in_name = cookie_manager.get('player_name')
    
    st.session_state.logout_in_progress = False

    live_state = get_live_state()
    players_db = get_players_db()
    
    mode = st.query_params.get("mode")
    if mode == "court":
        render_court_mode(live_state, players_db, cookie_manager)
    else:
        render_player_mode(live_state, players_db, cookie_manager)
