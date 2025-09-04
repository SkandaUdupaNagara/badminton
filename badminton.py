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
    INITIAL_ROSTER_JSON = st.secrets.app_secrets.initial_roster_json
except AttributeError:
    st.error("Your `secrets.toml` file is missing or misconfigured.")
    st.stop()


# --- Custom CSS ---
st.markdown("""<style>.main .block-container{padding:1rem 1rem 10rem}[data-testid=stVerticalBlock]>[data-testid=stVerticalBlock]>[data-testid=stVerticalBlock]>[data-testid=stVerticalBlock]>div:nth-child(1)>div{border-radius:.75rem;box-shadow:0 4px 6px rgba(0,0,0,.05);border:1px solid #e6e6e6}.stButton>button{border-radius:.5rem;font-weight:500}h4{font-size:1.25rem;font-weight:600;margin-bottom:.5rem}.player-pill{display:block;padding:8px 12px;margin:4px 0;border-radius:8px;background-color:#f0f2f6;font-weight:500;border:1px solid #ddd}.player-pill-chooser{background-color:#fff0c1;border:2px solid #ffbf00;font-weight:700}</style>""", unsafe_allow_html=True)

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
        if 'main_queue' not in state: state['main_queue'] = state.get('waiting_players', [])
        return state
    else: 
        INITIAL_ROSTER = json.loads(INITIAL_ROSTER_JSON)
        for player in INITIAL_ROSTER:
            if 'chooser_count' not in player: player['chooser_count'] = 0
            PLAYERS_COLLECTION_REF.document(str(player['id'])).set(player)
        default_state = {
            'attendees': [], 'finishers_queue': [], 'main_queue': [], 'active_games': {},
            'session_password': generate_password(), 'last_chooser_id': None
        }
        STATE_DOC_REF.set(default_state)
        return default_state

def generate_password(): return "".join(random.choices(string.digits, k=6))

def get_cookie_manager():
    return stx.CookieManager()

# ────────────────────────────────────────────────────────────────────────────────
# PLAYER & COURT MODES
# ────────────────────────────────────────────────────────────────────────────────
def render_player_mode(live_state, players_db, cookie_manager):
    if not st.session_state.player_logged_in_name:
        st.title("🏸 Player Attendance")
        st.write("Log in with the **last 4 digits** of your mobile number.")
        with st.form("player_login_form"):
            last_four_input = st.text_input("Enter the last 4 digits", max_chars=4)
            session_password = st.text_input("Today's Session Password", type="password")
            submitted = st.form_submit_button("Mark Attendance")
            if submitted:
                last_four = last_four_input.strip()
                if not (len(last_four) == 4 and last_four.isdigit()): st.error("Please enter exactly 4 digits.")
                else:
                    matching_players = [p for p in players_db.values() if p.get('mobile') == last_four]
                    if len(matching_players) == 0: st.error("No player found. Ask an admin to sync roster.")
                    elif len(matching_players) > 1: st.error("Multiple players share these digits. Contact an admin.")
                    elif session_password != live_state.get('session_password'): st.error("Incorrect password.")
                    else:
                        found_player = matching_players[0]
                        st.session_state.player_logged_in_name = found_player['name']
                        cookie_manager.set('player_name', found_player['name'], expires_at=datetime.datetime.now() + timedelta(hours=3))
                        player_id = found_player['id']
                        if player_id not in live_state.get('attendees', []):
                            STATE_DOC_REF.update({'attendees': firestore.ArrayUnion([player_id]),'main_queue': firestore.ArrayUnion([player_id])})
                            PLAYERS_COLLECTION_REF.document(str(player_id)).update({'check_in_time': firestore.SERVER_TIMESTAMP})
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
                    with st.spinner("Syncing..."):
                        roster = json.loads(INITIAL_ROSTER_JSON)
                        for player in roster: 
                            if 'chooser_count' not in player: player['chooser_count'] = 0
                            PLAYERS_COLLECTION_REF.document(str(player['id'])).set(player, merge=True)
                        st.cache_data.clear()
                    st.success("Roster Synced!"); time.sleep(1); st.rerun()
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
                STATE_DOC_REF.update({'attendees': [], 'finishers_queue': [], 'main_queue': [], 'active_games': {}, 'session_password': generate_password(), 'last_chooser_id': None})
                clear_game_log(); st.cache_data.clear(); st.rerun()
            if st.button("🔥 Clear Game Log", use_container_width=True, help="Deletes all game log entries."):
                clear_game_log(); st.toast("Game log cleared!", icon="🧹"); st.rerun()

def render_main_dashboard(live_state, players_db):
    courts_col, queue_col = st.columns([3, 1])
    with courts_col:
        tab_dashboard, tab_guest_checkout, tab_log = st.tabs(["🏟️ Courts", "👋 Guests & Check-out", "📊 Game Log"])

        with tab_dashboard:
            st.subheader("Active Courts")
            court_grid_cols = st.columns(2)
            for i in range(MAX_COURTS):
                cid_str, game = str(i + 1), live_state.get('active_games', {}).get(str(i + 1))
                with court_grid_cols[i % 2]:
                    with st.container(border=True):
                        st.markdown(f"<h4>Court {cid_str}</h4>", unsafe_allow_html=True)
                        if game:
                            team1_pids = [p['id'] for p in game.get('team1', [])]; team2_pids = [p['id'] for p in game.get('team2', [])]
                            team1_players = get_players_from_ids(team1_pids, players_db); team2_players = get_players_from_ids(team2_pids, players_db)
                            st.markdown(f"**Team 1:** {' & '.join([p['name'] for p in team1_players if p])}")
                            st.markdown(f"**Team 2:** {' & '.join([p['name'] for p in team2_players if p])}")
                            start_time = game.get('start_time');
                            if isinstance(start_time, str): start_time = datetime.datetime.fromisoformat(start_time)
                            elif not isinstance(start_time, datetime.datetime): start_time = datetime.datetime.now(timezone.utc)
                            elapsed = datetime.datetime.now(timezone.utc) - start_time
                            st.metric("Time Elapsed", f"{int(elapsed.total_seconds() // 60):02d}:{int(elapsed.total_seconds() % 60):02d}")
                            s_cols = st.columns(2)
                            t1s, t2s = s_cols[0].number_input("T1 Score", 0, step=1, key=f"t1s_{cid_str}"), s_cols[1].number_input("T2 Score", 0, step=1, key=f"t2s_{cid_str}")
                            if st.button("Log Score & Finish", key=f"log_{cid_str}", use_container_width=True, type="primary"):
                                live_state['active_games'].pop(cid_str)
                                winning_pids = team1_pids if t1s > t2s else team2_pids if t2s > t1s else []
                                losing_pids = team2_pids if t1s > t2s else team1_pids if t2s > t1s else team1_pids + team2_pids
                                winners = get_players_from_ids(winning_pids, players_db)
                                if len(winners) == 2:
                                    p1_count = winners[0].get('chooser_count', 0); p2_count = winners[1].get('chooser_count', 0)
                                    ordered_winners = [winners[0]['id'], winners[1]['id']] if p1_count <= p2_count else [winners[1]['id'], winners[0]['id']]
                                else: ordered_winners = winning_pids
                                new_finishers = ordered_winners + losing_pids
                                STATE_DOC_REF.update({'active_games': live_state['active_games'], 'finishers_queue': firestore.ArrayUnion(new_finishers)})
                                if ordered_winners: PLAYERS_COLLECTION_REF.document(str(ordered_winners[0])).update({'chooser_count': firestore.Increment(1)})
                                for pid in new_finishers: PLAYERS_COLLECTION_REF.document(str(pid)).update({'last_played': firestore.SERVER_TIMESTAMP})
                                log = {'finish_time': firestore.SERVER_TIMESTAMP, 'Duration': f"{int(elapsed.total_seconds() // 60)}m", 'Court': cid_str,
                                       'Team 1 Players': " & ".join([p['name'] for p in team1_players if p]), 'Team 2 Players': " & ".join([p['name'] for p in team2_players if p]),
                                       'Score': f"{t1s} - {t2s}", 'Winner': "Draw" if t1s == t2s else "Team 1" if t1s > t2s else "Team 2"}
                                LOG_COLLECTION_REF.add(log); st.rerun()
                        else: # Court is free
                            waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
                            if len(waiting_pids) < 4:
                                st.info("Court is available. Need at least 4 players waiting.")
                            else:
                                chooser_pid = waiting_pids[0]; chooser_player = players_db.get(str(chooser_pid))
                                st.success(f"👑 It's **{chooser_player.get('name', 'N/A')}'s** turn to choose.")
                                other_players = get_players_from_ids(waiting_pids[1:], players_db)
                                opts = {p['name']: p['id'] for p in other_players if p}
                                selected_names = st.multiselect(f"1. Select 3 players to join {chooser_player.get('name', 'N/A')}", options=opts.keys(), key=f"pl_sel_{cid_str}", max_selections=3)
                                if len(selected_names) == 3:
                                    team1_choices = [chooser_player['name']] + selected_names
                                    team1_names = st.multiselect("2. Select 2 players for Team 1", options=team1_choices, key=f"t1_sel_{cid_str}", max_selections=2)
                                    if len(team1_names) == 2:
                                        team2_names = [name for name in team1_choices if name not in team1_names]
                                        st.markdown(f"**Team 1:** {team1_names[0]} & {team1_names[1]}"); st.markdown(f"**Team 2:** {team2_names[0]} & {team2_names[1]}")
                                        if st.button("Start Game", key=f"start_manual_{cid_str}", use_container_width=True):
                                            all_pids = [chooser_player['id']] + [opts[name] for name in selected_names]
                                            team1_pids = [next(p['id'] for p in players_db.values() if p['name'] == name) for name in team1_names]
                                            team2_pids = [next(p['id'] for p in players_db.values() if p['name'] == name) for name in team2_names]
                                            live_state['active_games'][cid_str] = {'team1': get_players_from_ids(team1_pids, players_db), 'team2': get_players_from_ids(team2_pids, players_db), 'player_ids': all_pids, 'start_time': firestore.SERVER_TIMESTAMP}
                                            STATE_DOC_REF.update({'finishers_queue': firestore.ArrayRemove(all_pids), 'main_queue': firestore.ArrayRemove(all_pids), 'active_games': live_state['active_games']})
                                            for pid in all_pids: PLAYERS_COLLECTION_REF.document(str(pid)).update({'last_played': firestore.SERVER_TIMESTAMP})
                                            st.rerun()

        with tab_guest_checkout:
            st.subheader("Guest Check-in and Player Check-out")
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
                                    STATE_DOC_REF.update({'attendees': firestore.ArrayUnion([pid]), 'main_queue': firestore.ArrayUnion([pid])})
                                    st.session_state.show_confirm_for = None; st.cache_data.clear()
                                    st.toast(f"Guest {p.get('name')} checked in!", icon="👍"); st.rerun()
                            if is_present:
                                if st.button("Confirm Check-out", key=f"rem_{pid}", use_container_width=True):
                                    STATE_DOC_REF.update({'attendees': firestore.ArrayRemove([pid]), 'finishers_queue': firestore.ArrayRemove([pid]), 'main_queue': firestore.ArrayRemove([pid])})
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

    with queue_col:
        st.subheader("⏳ Waiting Queue")
        st.caption("Finishers move to the top, winners first.")
        waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
        waiting_players = get_players_from_ids(waiting_pids, players_db)
        if not waiting_players: st.info("Waiting list is empty.")
        else:
            for i, p in enumerate(waiting_players):
                if p:
                    is_chooser = (i == 0); icon = "👑 " if is_chooser else ""
                    st.markdown(f"<div class='player-pill {'player-pill-chooser' if is_chooser else ''}'>{i+1}. {icon}{p['name']}</div>", unsafe_allow_html=True)
            if live_state.get('finishers_queue'): st.markdown("---")
        
        if st.session_state.court_operator_logged_in in ADMIN_USERS:
            with st.expander("👑 Remove Player from Queue"):
                if not waiting_players:
                    st.write("Queue is empty.")
                else:
                    names_to_remove = st.multiselect("Select players to remove", [p['name'] for p in waiting_players])
                    if st.button("Remove Selected Players", disabled=not names_to_remove):
                        pids_to_remove = [p['id'] for p in waiting_players if p['name'] in names_to_remove]
                        STATE_DOC_REF.update({'attendees': firestore.ArrayRemove(pids_to_remove), 'finishers_queue': firestore.ArrayRemove(pids_to_remove), 'main_queue': firestore.ArrayRemove(pids_to_remove)})
                        for pid in pids_to_remove: PLAYERS_COLLECTION_REF.document(str(pid)).update({'check_in_time': None})
                        st.toast(f"Removed {', '.join(names_to_remove)} from the session.", icon="👋"); st.rerun()

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
