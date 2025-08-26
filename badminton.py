import streamlit as st
import time
import datetime
import pandas as pd
import random
import string
from typing import List, Dict, Any, Optional

# --- NEW: Firebase Imports ---
import firebase_admin
from firebase_admin import credentials, firestore
from streamlit_autorefresh import st_autorefresh

# ────────────────────────────────────────────────────────────────────────────────
# CONFIGURATION & INITIAL DATA
# ────────────────────────────────────────────────────────────────────────────────

# --- Page Config ---
st.set_page_config(page_title="Badminton Pro", layout="wide", initial_sidebar_state="expanded")

# --- Constants & Access Control ---
MAX_COURTS = 4
SKILL_MAP = {1: 'Beginner', 2: 'Intermediate', 3: 'Advanced'}
PASSWORD_REQUESTERS = ["Jag", "Chilli", "Raj", "Roopa", "Santhosh", "Skanda"]
ADMIN_USERS = ["Skanda", "Jag"]
ADMIN_PASSWORD = "Club2025Secret"  # IMPORTANT: Change this password

# --- Hard-coded Roster (Used only for the very first run) ---
INITIAL_ROSTER = [
    {'id': 999618798, 'name': 'Hari', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 992590180, 'name': 'Kiran', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 523873599, 'name': 'Sarvesh', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 923212060, 'name': 'Santhosh', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 29884897, 'name': 'Siddarth', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 457970730, 'name': 'Raj', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 836747093, 'name': 'Rajesh', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 875687516, 'name': 'Raghu', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 728233281, 'name': 'Sampath', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 496785155, 'name': 'Bala', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 22922751, 'name': 'Jag', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 930974748, 'name': 'Ruchi', 'gender': 'Women', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 282622456, 'name': 'Allwin', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 997347498, 'name': 'Arifha', 'gender': 'Women', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 866438678, 'name': 'Chilli', 'gender': 'Women', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 316362406, 'name': 'Eshwar', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 917977450, 'name': 'Ganesh', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 690316923, 'name': 'Mahesh', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 534985622, 'name': 'Nithin', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 352992803, 'name': 'Pradeep', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 717323928, 'name': 'Roopa', 'gender': 'Women', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 507883481, 'name': 'Sreedhar', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 353393848, 'name': 'Sushma', 'gender': 'Women', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 473846635, 'name': 'Ushakanth', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 11475433, 'name': 'Vidya', 'gender': 'Women', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 276495561, 'name': 'Vikramraj', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 335425513, 'name': 'Nihira', 'gender': 'Women', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 482910357, 'name': 'Skanda', 'gender': 'Men', 'skill': 2, 'last_played': None, 'is_guest': False,},
    {'id': 361855841, 'name': 'Guest1', 'gender': 'Men/Women', 'skill': 2, 'last_played': None, 'is_guest': True,},
    {'id': 73129631, 'name': 'Guest2', 'gender': 'Men/Women', 'skill': 2, 'last_played': None, 'is_guest': True,},
    {'id': 327817360, 'name': 'Guest3', 'gender': 'Men/Women', 'skill': 2, 'last_played': None, 'is_guest': True,},
    {'id': 235751907, 'name': 'Guest4', 'gender': 'Men/Women', 'skill': 2, 'last_played': None, 'is_guest': True,},
]

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
SESSION_DOC_REF = db.collection("session").document("current_state") if db else None

def serialize_timestamps(obj):
    if isinstance(obj, dict):
        return {k: serialize_timestamps(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serialize_timestamps(elem) for elem in obj]
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    return obj

def deserialize_timestamps(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and ('T' in v and ('Z' in v or '+' in v)):
                try: obj[k] = datetime.datetime.fromisoformat(v)
                except (ValueError, TypeError): pass
            else:
                obj[k] = deserialize_timestamps(v)
    elif isinstance(obj, list):
        return [deserialize_timestamps(elem) for elem in obj]
    return obj

def get_shared_state():
    """Fetch, validate, and deserialize the shared session state from Firestore."""
    if not SESSION_DOC_REF: return {}
    
    default_state = {
        'players_db': {p['id']: p for p in INITIAL_ROSTER},
        'attendees': [], 'waiting_players': [], 'active_games': {},
        'game_log': [], 'session_password': generate_password()
    }
    
    doc = SESSION_DOC_REF.get()
    if doc.exists:
        state = doc.to_dict()
        # --- ROBUSTNESS FIX: Ensure all essential keys exist ---
        updated = False
        for key, default_value in default_state.items():
            if key not in state:
                state[key] = default_value
                updated = True
        if updated:
            set_shared_state(state) # Heal the remote state if keys were missing
        return deserialize_timestamps(state)
    else:
        set_shared_state(default_state) # Create the document for the first time
        return default_state

def set_shared_state(state):
    """Serialize and update the shared session state in Firestore."""
    if SESSION_DOC_REF:
        SESSION_DOC_REF.set(serialize_timestamps(state))

# ────────────────────────────────────────────────────────────────────────────────
# SESSION STATE & AUTH
# ────────────────────────────────────────────────────────────────────────────────
def generate_password():
    return "".join(random.choices(string.digits, k=6))

def initialize_local_state():
    """Initializes browser-local session state (for UI interaction)."""
    if 'logged_in_user' not in st.session_state:
        st.session_state.logged_in_user = None
    if 'password_revealed' not in st.session_state:
        st.session_state.password_revealed = False
    if 'show_confirm_for' not in st.session_state:
        st.session_state.show_confirm_for = None

def render_login_page(shared_state):
    st.title("🏸 Badminton Pro Scheduler")
    st.write("Please log in to continue.")
    with st.form("login_form"):
        # --- ROBUSTNESS FIX: Use .get() to avoid KeyErrors ---
        player_db = shared_state.get('players_db', {})
        player_names = sorted([
            p.get('name') for p in player_db.values()
            if p.get('name') and not p.get('is_guest', False)
        ])
        
        selected_user = st.selectbox("Select your name", player_names)
        password = st.text_input("Session Password", type="password")
        submitted = st.form_submit_button("Login", use_container_width=True, type="primary")

        if submitted:
            if password == shared_state.get('session_password'):
                st.session_state.logged_in_user = selected_user
                player_obj = next((p for p in player_db.values() if p.get('name') == selected_user), None)
                if player_obj and player_obj.get('id') not in shared_state.get('attendees', []):
                    shared_state['players_db'][player_obj['id']]['check_in_time'] = datetime.datetime.now()
                    shared_state['attendees'].append(player_obj['id'])
                    add_to_waiting_list(player_obj['id'], shared_state)
                    set_shared_state(shared_state)
                    st.toast(f"Welcome, {selected_user}! You're checked in.", icon="✅")
                st.rerun()
            else:
                st.error("Incorrect password.")
    with st.expander("Need the Password?"):
        requester = st.selectbox("Confirm identity", options=PASSWORD_REQUESTERS, index=None)
        if requester:
            admin_pw = st.text_input("Enter Admin Password", type="password", key="admin_pw")
            if st.button("Verify & Show"):
                if admin_pw == ADMIN_PASSWORD: st.session_state.password_revealed = True
                else: st.error("Incorrect Admin Password.")
            if st.session_state.get("password_revealed"):
                st.success(f"Password: **{shared_state.get('session_password')}**")

# ────────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS (Now operate on the 'state' dictionary)
# ────────────────────────────────────────────────────────────────────────────────
Player = Dict[str, Any]

def get_player(pid: int, state: dict) -> Optional[Player]: return state.get('players_db', {}).get(pid)
def get_players_from_ids(pids: List[int], state: dict) -> List[Player]: return [p for pid in pids if (p := get_player(pid, state))]
def format_time_delta(delta: datetime.timedelta) -> str:
    total_seconds = int(delta.total_seconds());
    if total_seconds < 0: return "00:00"
    minutes, seconds = divmod(total_seconds, 60); return f"{minutes:02}:{seconds:02}"
def add_to_waiting_list(pid: int, state: dict):
    on_court_pids = {p for g in state.get('active_games', {}).values() for p in g.get('player_ids', [])}
    if pid not in state.get('waiting_players', []) and pid not in on_court_pids: state['waiting_players'].append(pid)
def remove_from_waiting_list(pids: List[int], state: dict):
    state['waiting_players'] = [pid for pid in state.get('waiting_players', []) if pid not in pids]
def update_last_played(pids: List[int], state: dict):
    now = datetime.datetime.now();
    for pid in pids:
        if p := get_player(pid, state): p['last_played'] = now
def get_fair_player_selection(state: dict) -> Optional[List[Player]]:
    if len(state.get('waiting_players', [])) < 4: return None
    players = get_players_from_ids(state.get('waiting_players', []), state)
    return sorted(players, key=lambda p: (0 if p.get('last_played') is None else 1, p.get('last_played') or datetime.datetime.min))[:4]
def create_balanced_teams(players: List[Player]) -> (List[Player], List[Player]):
    sp = sorted(players, key=lambda p: p.get('skill', 2), reverse=True); return [sp[0], sp[3]], [sp[1], sp[2]]
def start_game(court_id: int, players: List[Player], state: dict):
    team1, team2 = create_balanced_teams(players); pids = [p['id'] for p in players]
    remove_from_waiting_list(pids, state); update_last_played(pids, state)
    state['active_games'][court_id] = {'team1': team1, 'team2': team2, 'player_ids': pids, 'start_time': datetime.datetime.now()}
def end_game(court_id: int, t1_score: int, t2_score: int, state: dict):
    game = state.get('active_games', {}).pop(court_id, None)
    if game:
        finish_time = datetime.datetime.now()
        duration = finish_time - game.get('start_time', finish_time)
        duration_str = f"{int(duration.total_seconds() // 60)}m {int(duration.total_seconds() % 60)}s"
        winner = "Draw" if t1_score == t2_score else "Team 1" if t1_score > t2_score else "Team 2"
        log = {'Finish Time': finish_time, 'Duration': duration_str, 'Court': court_id,
               'Team 1 Players': " & ".join([p['name'] for p in game.get('team1', [])]),
               'Team 2 Players': " & ".join([p['name'] for p in game.get('team2', [])]),
               'Score': f"{t1_score} - {t2_score}", 'Winner': winner}
        state['game_log'].append(log)
        for pid in game.get('player_ids', []): add_to_waiting_list(pid, state)

# ────────────────────────────────────────────────────────────────────────────────
# UI RENDERING FUNCTIONS (Now accept 'state' dictionary)
# ────────────────────────────────────────────────────────────────────────────────
def render_sidebar(state):
    with st.sidebar:
        st.title("🏸 Badminton Pro")
        st.markdown(f"Welcome, **{st.session_state.logged_in_user}**!")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in_user = None; st.session_state.password_revealed = False; st.rerun()
        st.markdown("---")
        attendees = len(state.get('attendees', [])); waiting = len(state.get('waiting_players', [])); on_court = sum(len(g.get('player_ids', [])) for g in state.get('active_games', {}).values())
        c1, c2, c3 = st.columns(3); c1.metric("Present", attendees); c2.metric("Waiting", waiting); c3.metric("On Court", on_court)
        st.markdown("---")
        if st.session_state.logged_in_user in ADMIN_USERS:
            st.header("Admin Controls")
            if st.button("🔄 Reset Full Session", use_container_width=True, type="secondary"):
                current_players_db = state.get('players_db', {})
                new_state = {
                    'players_db': current_players_db,
                    'attendees': [], 'waiting_players': [], 'active_games': {},
                    'game_log': [], 'session_password': generate_password()
                }
                set_shared_state(new_state)
                st.rerun()

def render_main_dashboard(state):
    tab_dashboard, tab_guest_checkout, tab_log = st.tabs(["🏟️ Courts & Queue", "👋 Guests & Check-out", "📊 Game Log"])
    # (Rest of the main dashboard rendering code is substantively the same, just with .get() for safety)
    with tab_dashboard:
        st.subheader("⏳ Waiting Queue")
        sorted_waiting = sorted(get_players_from_ids(state.get('waiting_players', []), state), key=lambda p: (0 if p.get('last_played') is None else 1, p.get('last_played') or datetime.datetime.min))
        if not sorted_waiting: st.info("Waiting list is empty.")
        else:
            pills = [f"<div class='player-pill' style='{'border: 2px solid #9067C6;' if i<4 else ''}'>{i+1}. {p['name']}</div>" for i, p in enumerate(sorted_waiting)]
            st.markdown("".join(pills), unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True); st.subheader("🏸 Active Courts")
        court_cols = st.columns(2)
        for i in range(MAX_COURTS):
            cid, game = i + 1, state.get('active_games', {}).get(i + 1)
            with court_cols[i % 2]:
                with st.container(border=True):
                    st.markdown(f"<h4>Court {cid}</h4>", unsafe_allow_html=True)
                    if game:
                        st.markdown(f"**Team 1:** {' & '.join([p['name'] for p in game.get('team1', [])])}")
                        st.markdown(f"**Team 2:** {' & '.join([p['name'] for p in game.get('team2', [])])}")
                        st.metric("Time Elapsed", format_time_delta(datetime.datetime.now() - game.get('start_time', datetime.datetime.now())))
                        s_cols = st.columns(2)
                        t1s, t2s = s_cols[0].number_input("T1 Score", 0, step=1, key=f"t1s_{cid}"), s_cols[1].number_input("T2 Score", 0, step=1, key=f"t2s_{cid}")
                        if st.button("Log Score & Finish", key=f"log_{cid}", use_container_width=True, type="primary"):
                            end_game(cid, t1s, t2s, state); set_shared_state(state); st.rerun()
                    else:
                        st.success("Court is available!")
                        next_up = get_fair_player_selection(state)
                        if st.button("Auto Assign", key=f"auto_{cid}", use_container_width=True, type="primary", disabled=(not next_up)):
                            start_game(cid, next_up, state); set_shared_state(state); st.rerun()
                        if not next_up: st.caption("Need 4+ players.")
                        with st.expander("Manual Selection"):
                            opts = [(p['id'], p['name']) for p in sorted_waiting]
                            sel = st.multiselect("Select 4", opts, format_func=lambda t: t[1], key=f"msel_{cid}", max_selections=4)
                            if st.button("Assign", key=f"mbtn_{cid}", use_container_width=True, disabled=(len(sel)!=4)):
                                start_game(cid, get_players_from_ids([t[0] for t in sel], state), state); set_shared_state(state); st.rerun()
    with tab_guest_checkout:
        st.subheader("Guest Check-in and Player Check-out")
        search = st.text_input("Search player...", placeholder="Type name...")
        cols = st.columns(3)
        filtered = [p for p in state.get('players_db', {}).values() if search.lower() in p.get('name', '').lower()]
        for i, p in enumerate(sorted(filtered, key=lambda p: p.get('name', ''))):
            pid, is_present = p['id'], p['id'] in state.get('attendees', [])
            with cols[i % 3]:
                if st.button(f"{'✅ ' if is_present else ''}{p.get('name')}", key=f"btn_{pid}", use_container_width=True):
                    st.session_state.show_confirm_for = pid if st.session_state.show_confirm_for != pid else None
                if st.session_state.show_confirm_for == pid:
                    with st.container(border=True):
                        st.write(f"**Status:** {'Present' if is_present else 'Not checked in'}")
                        if p.get('is_guest') and not is_present:
                            skill = st.select_slider("Skill", [1,2,3], p.get('skill',2), format_func=SKILL_MAP.get, key=f"sk_{pid}")
                            gender = st.radio("Gender", ["Men","Women"], 0 if p.get('gender')!='Women' else 1, key=f"gen_{pid}", horizontal=True)
                            if st.button("Confirm Guest Check-in", key=f"cf_{pid}", type="primary", use_container_width=True):
                                state['players_db'][pid].update({'skill': skill, 'gender': gender, 'check_in_time': datetime.datetime.now()})
                                state['attendees'].append(pid); add_to_waiting_list(pid, state)
                                st.session_state.show_confirm_for=None; set_shared_state(state); st.toast(f"Guest in!", icon="👍"); st.rerun()
                        if is_present:
                            if st.button("Confirm Check-out", key=f"rem_{pid}", use_container_width=True):
                                if 'check_in_time' in state['players_db'][pid]: state['players_db'][pid]['check_in_time'] = None
                                state['attendees'] = [att_id for att_id in state['attendees'] if att_id != pid]; remove_from_waiting_list([pid], state)
                                st.session_state.show_confirm_for=None; set_shared_state(state); st.toast(f"{p.get('name')} out.", icon="👋"); st.rerun()
    with tab_log:
        st.subheader("📊 Completed Games Log")
        if not state.get('game_log', []): st.info("No games logged yet.")
        else:
            df = pd.DataFrame(state.get('game_log', []))
            df['Finish Time'] = pd.to_datetime(df['Finish Time']).dt.strftime('%H:%M')
            df = df[['Finish Time', 'Duration', 'Court', 'Team 1 Players', 'Team 2 Players', 'Score', 'Winner']]
            st.dataframe(df.iloc[::-1], use_container_width=True, hide_index=True)
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Log (CSV)", csv, f"badminton_log_{datetime.date.today()}.csv", "text/csv", use_container_width=True)


# ────────────────────────────────────────────────────────────────────────────────
# MAIN APP EXECUTION
# ────────────────────────────────────────────────────────────────────────────────
if not db:
    st.error("Could not connect to Firebase. App cannot continue.")
else:
    initialize_local_state()
    shared_state = get_shared_state()
    
    if not st.session_state.logged_in_user:
        render_login_page(shared_state)
    else:
        render_sidebar(shared_state)
        render_main_dashboard(shared_state)
        st_autorefresh(interval=5000, key="firestore_refresher")
