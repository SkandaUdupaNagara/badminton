import streamlit as st
import time
import datetime
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

# --- Firebase Integration (New Granular Structure) ---
def init_firebase():
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(dict(st.secrets["firebase_credentials"]))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Firebase initialization failed: {e}"); return None

db = init_firebase()

# --- NEW: References to specific documents and collections ---
STATE_DOC_REF = db.collection("session").document("live_state") if db else None
PLAYERS_COLLECTION_REF = db.collection("session").document("live_state").collection("players") if db else None
LOG_COLLECTION_REF = db.collection("session").document("live_state").collection("game_log") if db else None

# --- NEW: Caching to reduce database reads ---
@st.cache_data(ttl=30) # Cache player data for 30 seconds
def get_players_db():
    if not PLAYERS_COLLECTION_REF: return {}
    docs = PLAYERS_COLLECTION_REF.stream()
    return {doc.id: doc.to_dict() for doc in docs}

def get_live_state():
    if not STATE_DOC_REF: return {}
    doc = STATE_DOC_REF.get()
    if doc.exists:
        return doc.to_dict()
    else: # First time setup
        INITIAL_ROSTER = json.loads(INITIAL_ROSTER_JSON)
        for player in INITIAL_ROSTER:
            PLAYERS_COLLECTION_REF.document(str(player['id'])).set(player)
        
        default_state = {
            'attendees': [], 'waiting_players': [], 'active_games': {},
            'session_password': generate_password()
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
        # --- MODIFIED: Changed from selectbox to text_input ---
        typed_name = st.text_input("Enter your name")
        password = st.text_input("Session Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

        if submitted:
            # --- MODIFIED: Added validation for the typed name ---
            user_name_to_login = None
            found_player = None
            
            if typed_name:
                # Case-insensitive search for the player
                for player in players_db.values():
                    if player.get('name', '').lower() == typed_name.strip().lower():
                        found_player = player
                        user_name_to_login = player['name'] # Use the correctly cased name from DB
                        break
            
            if not found_player:
                st.error("Player not found. Please check your spelling and try again.")
            elif password != live_state.get('session_password'):
                st.error("Incorrect session password.")
            else:
                # Login successful
                st.session_state.logged_in_user = user_name_to_login
                
                # Auto-check-in logic
                if found_player['id'] not in live_state.get('attendees', []):
                    player_id = found_player['id']
                    # Perform targeted updates
                    STATE_DOC_REF.update({
                        'attendees': firestore.ArrayUnion([player_id]),
                        'waiting_players': firestore.ArrayUnion([player_id])
                    })
                    PLAYERS_COLLECTION_REF.document(str(player_id)).update({'check_in_time': firestore.SERVER_TIMESTAMP})
                    st.toast(f"Welcome, {user_name_to_login}! You're checked in.", icon="✅")
                    st.rerun()
                else:
                    st.rerun() # Already checked in, just log in

    with st.expander("Need the Password?"):
        requester = st.selectbox("Confirm identity", options=PASSWORD_REQUESTERS, index=None)
        if requester:
            admin_pw = st.text_input("Enter Admin Password", type="password", key="admin_pw")
            if st.button("Verify & Show"):
                if admin_pw == ADMIN_PASSWORD:
                    st.session_state.password_revealed = True
                else:
                    st.error("Incorrect Admin Password.")
            if st.session_state.get("password_revealed"):
                st.success(f"Password: **{live_state.get('session_password')}**")


# ────────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS (Adapted for new structure)
# ────────────────────────────────────────────────────────────────────────────────
def get_players_from_ids(pids: List[int], players_db: dict) -> List[dict]:
    return [players_db.get(str(pid)) for pid in pids if str(pid) in players_db]

def get_fair_player_selection(live_state: dict, players_db: dict) -> Optional[List[dict]]:
    waiting_pids = live_state.get('waiting_players', [])
    if len(waiting_pids) < 4: return None
    players = get_players_from_ids(waiting_pids, players_db)
    return sorted(players, key=lambda p: (0 if p.get('last_played') is None else 1, p.get('last_played') or datetime.datetime.min))[:4]

def create_balanced_teams(players: List[dict]) -> (List[dict], List[dict]):
    sp = sorted(players, key=lambda p: p.get('skill', 2), reverse=True); return [sp[0], sp[3]], [sp[1], sp[2]]

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
                    'session_password': generate_password()
                })
                # This part can be slow if the log is huge.
                # Consider if you really need to clear it every time.
                # for doc in LOG_COLLECTION_REF.stream(): doc.reference.delete()
                st.cache_data.clear(); st.rerun()

def render_main_dashboard(live_state, players_db):
    tab_dashboard, tab_guest_checkout, tab_log = st.tabs(["🏟️ Courts & Queue", "👋 Guests & Check-out", "📊 Game Log"])
    with tab_dashboard:
        st.subheader("⏳ Waiting Queue")
        sorted_waiting = sorted(get_players_from_ids(live_state.get('waiting_players', []), players_db), key=lambda p: (0 if p.get('last_played') is None else 1, p.get('last_played') or datetime.datetime.min))
        if not sorted_waiting: st.info("Waiting list is empty.")
        else:
            pills = [f"<div class='player-pill' style='{'border: 2px solid #9067C6;' if i<4 else ''}'>{i+1}. {p['name']}</div>" for i, p in enumerate(sorted_waiting)]
            st.markdown("".join(pills), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True); st.subheader("🏸 Active Courts")
        court_cols = st.columns(2)
        for i in range(MAX_COURTS):
            cid_str, game = str(i + 1), live_state.get('active_games', {}).get(str(i + 1))
            with court_cols[i % 2]:
                with st.container(border=True):
                    st.markdown(f"<h4>Court {cid_str}</h4>", unsafe_allow_html=True)
                    if game:
                        team1_players = get_players_from_ids([p['id'] for p in game.get('team1', [])], players_db)
                        team2_players = get_players_from_ids([p['id'] for p in game.get('team2', [])], players_db)
                        st.markdown(f"**Team 1:** {' & '.join([p['name'] for p in team1_players])}")
                        st.markdown(f"**Team 2:** {' & '.join([p['name'] for p in team2_players])}")
                        start_time = game.get('start_time', datetime.datetime.now())
                        if isinstance(start_time, str): start_time = datetime.datetime.fromisoformat(start_time)
                        st.metric("Time Elapsed", f"{int((datetime.datetime.now(start_time.tzinfo) - start_time).total_seconds() // 60):02d}:{int((datetime.datetime.now(start_time.tzinfo) - start_time).total_seconds() % 60):02d}")
                        s_cols = st.columns(2)
                        t1s, t2s = s_cols[0].number_input("T1 Score", 0, step=1, key=f"t1s_{cid_str}"), s_cols[1].number_input("T2 Score", 0, step=1, key=f"t2s_{cid_str}")
                        if st.button("Log Score & Finish", key=f"log_{cid_str}", use_container_width=True, type="primary"):
                            game_to_log = live_state['active_games'].pop(cid_str)
                            all_player_ids = game_to_log.get('player_ids', [])
                            live_state['waiting_players'].extend(all_player_ids)
                            STATE_DOC_REF.update({'active_games': live_state['active_games'], 'waiting_players': live_state['waiting_players']})
                            for pid in all_player_ids: PLAYERS_COLLECTION_REF.document(str(pid)).update({'last_played': firestore.SERVER_TIMESTAMP})
                            finish_time = datetime.datetime.now()
                            duration = finish_time - start_time
                            log = {'Finish Time': finish_time, 'Duration': f"{int(duration.total_seconds() // 60)}m {int(duration.total_seconds() % 60)}s", 'Court': cid_str,
                                   'Team 1 Players': " & ".join([p['name'] for p in team1_players]), 'Team 2 Players': " & ".join([p['name'] for p in team2_players]),
                                   'Score': f"{t1s} - {t2s}", 'Winner': "Draw" if t1s == t2s else "Team 1" if t1s > t2s else "Team 2"}
                            LOG_COLLECTION_REF.add(log)
                            st.rerun()
                    else: # Court is free
                        st.success("Court is available!")
                        next_up = get_fair_player_selection(live_state, players_db)
                        if st.button("Auto Assign", key=f"auto_{cid_str}", use_container_width=True, type="primary", disabled=(not next_up)):
                            team1, team2 = create_balanced_teams(next_up); pids = [p['id'] for p in next_up]
                            live_state['waiting_players'] = [pid for pid in live_state['waiting_players'] if pid not in pids]
                            live_state['active_games'][cid_str] = {'team1': team1, 'team2': team2, 'player_ids': pids, 'start_time': firestore.SERVER_TIMESTAMP}
                            STATE_DOC_REF.update({'waiting_players': live_state['waiting_players'], 'active_games': live_state['active_games']})
                            for pid in pids: PLAYERS_COLLECTION_REF.document(str(pid)).update({'last_played': firestore.SERVER_TIMESTAMP})
                            st.rerun()
    with tab_log:
        st.subheader("📊 Completed Games Log")
        log_docs = (
                LOG_COLLECTION_REF
                .order_by("`Finish Time`", direction=firestore.Query.DESCENDING)
                .stream())
        log_data = [doc.to_dict() for doc in log_docs]
        if not log_data: st.info("No games logged yet.")
        else:
            df = pd.DataFrame(log_data)
            df['Finish Time'] = pd.to_datetime(df['Finish Time']).dt.strftime('%H:%M')
            df = df[['Finish Time', 'Duration', 'Court', 'Team 1 Players', 'Team 2 Players', 'Score', 'Winner']]
            st.dataframe(df, use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Log (CSV)", csv, f"badminton_log_{datetime.date.today().strftime('%Y-%m-%d')}.csv", "text/csv")
    
    # The Guests & Check-out tab would require more significant refactoring to work with the new state model.
    # For now, it's removed to focus on the core functionality. It can be added back if needed.


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
        st_autorefresh(interval=10000, key="firestore_refresher")
