import streamlit as st
import time
import datetime
from datetime import timezone
import pandas as pd
import random
import string
import json
from typing import List, Dict, Any, Optional

# --- Firebase Imports ---
import firebase_admin
from firebase_admin import credentials, firestore
from streamlit_autorefresh import st_autorefresh

# ────────────────────────────────────────────────────────────────────────────────
# CONFIGURATION & INITIAL DATA
# ────────────────────────────────────────────────────────────────────────────────

# --- Page Config ---
st.set_page_config(page_title="Acers Badminton Club 2025", layout="wide", initial_sidebar_state="expanded")

# --- Constants & Secrets ---
MAX_COURTS = 4
SKILL_MAP = {1: 'Beginner', 2: 'Intermediate', 3: 'Advanced'}

try:
    ADMIN_PASSWORD = st.secrets.app_secrets.admin_password
    PASSWORD_REQUESTERS = st.secrets.app_secrets.password_requesters
    ADMIN_USERS = st.secrets.app_secrets.admin_users
    INITIAL_ROSTER_JSON = st.secrets.app_secrets.initial_roster_json
except AttributeError:
    st.error("Your `secrets.toml` file is missing or misconfigured under the `[app_secrets]` section.")
    st.stop()


# --- Custom CSS ---
st.markdown("""<style>.main .block-container{padding:2rem 1rem 10rem}[data-testid=stVerticalBlock]>[data-testid=stVerticalBlock]>[data-testid=stVerticalBlock]>[data-testid=stVerticalBlock]>div:nth-child(1)>div{border-radius:.75rem;box-shadow:0 4px 6px rgba(0,0,0,.05);border:1px solid #e6e6e6}.stButton>button{border-radius:.5rem;font-weight:500}.player-pill{display:inline-block;padding:6px 12px;margin:4px 4px 4px 0;border-radius:16px;background-color:#f0f2f6;font-weight:500;border:1px solid #ddd}h4{font-size:1.25rem;font-weight:600;margin-bottom:.5rem}</style>""", unsafe_allow_html=True)

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
        return doc.to_dict()
    else:
        INITIAL_ROSTER = json.loads(INITIAL_ROSTER_JSON)
        for player in INITIAL_ROSTER:
            PLAYERS_COLLECTION_REF.document(str(player['id'])).set(player)
        default_state = {
            'attendees': [], 'waiting_players': [], 'active_games': {},
            'session_password': generate_password(), 'chooser': None # NEW: For winner's choice
        }
        STATE_DOC_REF.set(default_state)
        return default_state

# ────────────────────────────────────────────────────────────────────────────────
# SESSION STATE & AUTH
# ────────────────────────────────────────────────────────────────────────────────
def generate_password(): return "".join(random.choices(string.digits, k=6))

def initialize_local_state():
    if 'logged_in_user' not in st.session_state: st.session_state.logged_in_user = None
    if 'password_revealed' not in st.session_state: st.session_state.password_revealed = False
    if 'show_confirm_for' not in st.session_state: st.session_state.show_confirm_for = None

def render_login_page(live_state, players_db):
    st.title("🏸 Acers Badminton Club Scheduler")
    st.write("Please log in to continue.")
    with st.form("login_form"):
        typed_name = st.text_input("Enter your name")
        password = st.text_input("Session Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

        if submitted:
            user_name_to_login, found_player = None, None
            if typed_name:
                for player in players_db.values():
                    if player.get('name', '').lower() == typed_name.strip().lower():
                        found_player = player; user_name_to_login = player['name']; break
            if not found_player:
                st.error("Player not found. Please check your spelling and try again.")
            elif password != live_state.get('session_password'):
                st.error("Incorrect session password.")
            else:
                st.session_state.logged_in_user = user_name_to_login
                
                # Check if this is the first player to log in
                is_first_login = not live_state.get('attendees')
                
                if found_player['id'] not in live_state.get('attendees', []):
                    player_id = found_player['id']
                    update_data = {
                        'attendees': firestore.ArrayUnion([player_id]),
                        'waiting_players': firestore.ArrayUnion([player_id])
                    }
                    # If first login, set as the chooser for Court 1
                    if is_first_login:
                        update_data['chooser'] = {'player_id': player_id, 'court_id': '1'}
                        st.toast(f"Welcome, {user_name_to_login}! You're the first, you choose the first game on Court 1.", icon="🎉")
                    else:
                         st.toast(f"Welcome, {user_name_to_login}! You're checked in.", icon="✅")

                    STATE_DOC_REF.update(update_data)
                    PLAYERS_COLLECTION_REF.document(str(player_id)).update({'check_in_time': firestore.SERVER_TIMESTAMP})
                    st.rerun()
                else:
                    st.rerun()

    with st.expander("Need the Password?", expanded=st.session_state.get("password_revealed", False)):
        requester = st.selectbox("Confirm identity", options=PASSWORD_REQUESTERS, index=None)
        if requester:
            admin_pw = st.text_input("Enter Admin Password", type="password", key="admin_pw")
            if st.button("Verify & Show"):
                if admin_pw == ADMIN_PASSWORD:
                    st.session_state.password_revealed = True
                    st.rerun()
                else:
                    st.error("Incorrect Admin Password.")
            if st.session_state.get("password_revealed"):
                st.success(f"Password: **{live_state.get('session_password')}**")

# ────────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ────────────────────────────────────────────────────────────────────────────────
def get_players_from_ids(pids: List[int], players_db: dict) -> List[dict]:
    return [players_db.get(str(pid)) for pid in pids if str(pid) in players_db]

def clear_game_log():
    if not LOG_COLLECTION_REF: return
    for doc in LOG_COLLECTION_REF.stream():
        doc.reference.delete()

# ────────────────────────────────────────────────────────────────────────────────
# UI RENDERING FUNCTIONS
# ────────────────────────────────────────────────────────────────────────────────
def render_sidebar(live_state, players_db):
    with st.sidebar:
        st.title("🏸 Acers Badminton Club")
        st.markdown(f"Welcome, **{st.session_state.logged_in_user}**!")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in_user = None; st.rerun()
        st.markdown("---")
        attendees, waiting = len(live_state.get('attendees', [])), len(live_state.get('waiting_players', []))
        on_court = sum(len(g.get('player_ids', [])) for g in live_state.get('active_games', {}).values())
        c1, c2, c3 = st.columns(3); c1.metric("Present", attendees); c2.metric("Waiting", waiting); c3.metric("On Court", on_court)
        st.markdown("---")
        if st.session_state.logged_in_user in ADMIN_USERS:
            st.header("Admin Controls")
            if st.button("🔄 Reset Full Session", use_container_width=True, type="secondary"):
                STATE_DOC_REF.update({
                    'attendees': [], 'waiting_players': [], 'active_games': {},
                    'session_password': generate_password(), 'chooser': None
                })
                clear_game_log(); st.cache_data.clear(); st.rerun()
            if st.button("🔥 Clear Game Log", use_container_width=True, help="Deletes all game log entries."):
                clear_game_log(); st.toast("Game log cleared!", icon="🧹"); st.rerun()

def render_main_dashboard(live_state, players_db):
    logged_in_player = next((p for p in players_db.values() if p['name'] == st.session_state.logged_in_user), None)
    
    tab_dashboard, tab_guest_checkout, tab_log = st.tabs(["🏟️ Courts & Queue", "👋 Guests & Check-out", "📊 Game Log"])
    
    with tab_dashboard:
        st.subheader("⏳ Waiting Queue (Winners move to the top)")
        waiting_pids = live_state.get('waiting_players', [])
        waiting_players = get_players_from_ids(waiting_pids, players_db)
        if not waiting_players: st.info("Waiting list is empty.")
        else:
            pills = [f"<div class='player-pill'>{i+1}. {p['name']}</div>" for i, p in enumerate(waiting_players)]
            st.markdown("".join(pills), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True); st.subheader("🏸 Active Courts")
        
        court_cols = st.columns(2)
        for i in range(MAX_COURTS):
            cid_str, game = str(i + 1), live_state.get('active_games', {}).get(str(i + 1))
            with court_cols[i % 2]:
                with st.container(border=True):
                    st.markdown(f"<h4>Court {cid_str}</h4>", unsafe_allow_html=True)
                    if game:
                        team1_pids = [p['id'] for p in game.get('team1', [])]; team2_pids = [p['id'] for p in game.get('team2', [])]
                        team1_players = get_players_from_ids(team1_pids, players_db); team2_players = get_players_from_ids(team2_pids, players_db)
                        st.markdown(f"**Team 1:** {' & '.join([p['name'] for p in team1_players])}")
                        st.markdown(f"**Team 2:** {' & '.join([p['name'] for p in team2_players])}")
                        start_time = game.get('start_time');
                        if isinstance(start_time, str): start_time = datetime.datetime.fromisoformat(start_time)
                        elif not isinstance(start_time, datetime.datetime): start_time = datetime.datetime.now(timezone.utc)
                        elapsed = datetime.datetime.now(timezone.utc) - start_time
                        st.metric("Time Elapsed", f"{int(elapsed.total_seconds() // 60):02d}:{int(elapsed.total_seconds() % 60):02d}")
                        s_cols = st.columns(2)
                        t1s, t2s = s_cols[0].number_input("T1 Score", 0, step=1, key=f"t1s_{cid_str}"), s_cols[1].number_input("T2 Score", 0, step=1, key=f"t2s_{cid_str}")
                        if st.button("Log Score & Finish", key=f"log_{cid_str}", use_container_width=True, type="primary"):
                            game_to_log = live_state['active_games'].pop(cid_str)
                            winning_pids = team1_pids if t1s > t2s else team2_pids if t2s > t1s else []
                            losing_pids = team2_pids if t1s > t2s else team1_pids if t2s > t1s else team1_pids + team2_pids
                            chooser_pid = None
                            if winning_pids:
                                chooser_pid = logged_in_player['id'] if logged_in_player['id'] in winning_pids else winning_pids[0]
                            
                            current_waiting = [pid for pid in live_state.get('waiting_players', []) if pid not in winning_pids + losing_pids]
                            new_waiting_list = winning_pids + current_waiting + losing_pids
                            
                            STATE_DOC_REF.update({
                                'active_games': live_state['active_games'], 
                                'waiting_players': new_waiting_list,
                                'chooser': {'player_id': chooser_pid, 'court_id': cid_str} if chooser_pid else None
                            })
                            for pid in winning_pids + losing_pids: PLAYERS_COLLECTION_REF.document(str(pid)).update({'last_played': firestore.SERVER_TIMESTAMP})
                            log = {'finish_time': firestore.SERVER_TIMESTAMP, 'Duration': f"{int(elapsed.total_seconds() // 60)}m", 'Court': cid_str,
                                   'Team 1 Players': " & ".join([p['name'] for p in team1_players]), 'Team 2 Players': " & ".join([p['name'] for p in team2_players]),
                                   'Score': f"{t1s} - {t2s}", 'Winner': "Draw" if t1s == t2s else "Team 1" if t1s > t2s else "Team 2"}
                            LOG_COLLECTION_REF.add(log); st.rerun()
                    else: # Court is free
                        chooser = live_state.get('chooser')
                        if chooser and chooser['court_id'] == cid_str:
                            chooser_player = players_db.get(str(chooser['player_id']))
                            if logged_in_player and chooser_player and logged_in_player['id'] == chooser_player['id']:
                                st.success(f"Your turn, {chooser_player['name']}! Form the teams for this court.")
                                other_players = [p for p in waiting_players if p['id'] != chooser_player['id']]
                                opts = {p['name']: p['id'] for p in other_players}
                                selected_names = st.multiselect("1. Select 3 other players", options=opts.keys(), key=f"player_sel_{cid_str}", max_selections=3)
                                if len(selected_names) == 3:
                                    team1_choices = [chooser_player['name']] + selected_names
                                    team1_names = st.multiselect("2. Select 2 players for your team (Team 1)", options=team1_choices, key=f"t1_sel_{cid_str}", max_selections=2)
                                    if len(team1_names) == 2:
                                        team2_names = [name for name in team1_choices if name not in team1_names]
                                        st.markdown(f"**Team 1:** {team1_names[0]} & {team1_names[1]}")
                                        st.markdown(f"**Team 2:** {team2_names[0]} & {team2_names[1]}")
                                        if st.button("Start Game", key=f"start_manual_{cid_str}", use_container_width=True):
                                            all_pids = [chooser_player['id']] + [opts[name] for name in selected_names]
                                            team1_pids = [players_db[str(opts[name])]['id'] if name != chooser_player['name'] else chooser_player['id'] for name in team1_names]
                                            team2_pids = [players_db[str(opts[name])]['id'] if name != chooser_player['name'] else chooser_player['id'] for name in team2_names]
                                            
                                            live_state['active_games'][cid_str] = {
                                                'team1': get_players_from_ids(team1_pids, players_db), 
                                                'team2': get_players_from_ids(team2_pids, players_db),
                                                'player_ids': all_pids, 
                                                'start_time': firestore.SERVER_TIMESTAMP
                                            }
                                            STATE_DOC_REF.update({
                                                'waiting_players': firestore.ArrayRemove(all_pids),
                                                'active_games': live_state['active_games'],
                                                'chooser': None
                                            })
                                            for pid in all_pids: PLAYERS_COLLECTION_REF.document(str(pid)).update({'last_played': firestore.SERVER_TIMESTAMP})
                                            st.rerun()
                            else:
                                st.info(f"Waiting for **{chooser_player['name']}** to pick players for this court.")
                        else:
                            st.info("Court is available. A winner from a previous game needs to form the teams.")

    with tab_guest_checkout:
        st.subheader("Guest Check-in and Player Check-out")
        # (This tab's logic remains the same as previous version)
        search = st.text_input("Search for a player...", placeholder="Type name...", key="checkout_search")
        cols = st.columns(3)
        filtered = [p for p in players_db.values() if search.lower() in p.get('name', '').lower()]
        for i, p in enumerate(sorted(filtered, key=lambda x: x.get('name', ''))):
            pid, is_present = p['id'], p['id'] in live_state.get('attendees', [])
            with cols[i % 3]:
                if st.button(f"{'✅ ' if is_present else ''}{p.get('name')}", key=f"btn_{pid}", use_container_width=True):
                    st.session_state.show_confirm_for = pid if st.session_state.show_confirm_for != pid else None
                if st.session_state.show_confirm_for == pid:
                    with st.container(border=True):
                        st.write(f"**Status:** {'Present' if is_present else 'Not checked in'}")
                        if p.get('is_guest') and not is_present:
                            st.markdown("**Guest Check-in Options:**")
                            skill = st.select_slider("Skill", [1, 2, 3], p.get('skill', 2), format_func=SKILL_MAP.get, key=f"sk_{pid}")
                            gender = st.radio("Gender", ["Men", "Women"], 0 if p.get('gender') != 'Women' else 1, key=f"gen_{pid}", horizontal=True)
                            if st.button("Confirm Guest Check-in", key=f"cf_{pid}", type="primary", use_container_width=True):
                                PLAYERS_COLLECTION_REF.document(str(pid)).update({'skill': skill, 'gender': gender, 'check_in_time': firestore.SERVER_TIMESTAMP})
                                STATE_DOC_REF.update({'attendees': firestore.ArrayUnion([pid]), 'waiting_players': firestore.ArrayUnion([pid])})
                                st.session_state.show_confirm_for = None; st.cache_data.clear()
                                st.toast(f"Guest {p.get('name')} checked in!", icon="👍"); st.rerun()
                        if is_present:
                            if st.button("Confirm Check-out", key=f"rem_{pid}", use_container_width=True):
                                STATE_DOC_REF.update({'attendees': firestore.ArrayRemove([pid]), 'waiting_players': firestore.ArrayRemove([pid])})
                                PLAYERS_COLLECTION_REF.document(str(pid)).update({'check_in_time': None})
                                st.session_state.show_confirm_for = None; st.cache_data.clear()
                                st.toast(f"{p.get('name')} checked out.", icon="👋"); st.rerun()

    with tab_log:
        st.subheader("📊 Completed Games Log")
        log_docs = LOG_COLLECTION_REF.order_by("finish_time", direction=firestore.Query.DESCENDING).stream()
        log_data = [doc.to_dict() for doc in log_docs]
        if not log_data: st.info("No games logged yet.")
        else:
            df = pd.DataFrame(log_data)
            df['finish_time'] = pd.to_datetime(df['finish_time']).dt.tz_convert('Europe/London').dt.strftime('%a, %d %b %Y, %H:%M')
            df.rename(columns={'finish_time': 'Finish Time'}, inplace=True)
            df = df[['Finish Time', 'Duration', 'Court', 'Team 1 Players', 'Team 2 Players', 'Score', 'Winner']]
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Log (CSV)", csv, f"badminton_log_{datetime.date.today().strftime('%Y-%m-%d')}.csv", "text/csv")


# ────────────────────────────────────────────────────────────────────────────────
# MAIN APP EXECUTION
# ────────────────────────────────────────────────────────────────────────────────
if not db:
    st.error("Could not connect to Firebase.")
else:
    initialize_local_state()
    live_state = get_live_state()
    players_db = get_players_db()
    
    if not st.session_state.logged_in_user:
        render_login_page(live_state, players_db)
    else:
        render_sidebar(live_state, players_db)
        render_main_dashboard(live_state, players_db)
        st_autorefresh(interval=5000, key="firestore_refresher")
