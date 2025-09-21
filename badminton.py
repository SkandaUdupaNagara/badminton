import streamlit as st
import time
import datetime
from datetime import timezone, timedelta
import pandas as pd
import random
import string
from typing import List, Dict, Any, Optional
from itertools import combinations
from collections import defaultdict

# --- Firebase Imports ---
import firebase_admin
from firebase_admin import credentials, firestore
from streamlit_autorefresh import st_autorefresh

# --- Additional Imports ---
import extra_streamlit_components as stx
from streamlit_dnd import st_dnd  # Drag-and-Drop functionality

# ────────────────────────────────────────────────────────────────────────────────
# CONFIGURATION & INITIAL DATA
# ────────────────────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Acers Badminton Club 2025", layout="wide", initial_sidebar_state="expanded")

# --- Constants & Secrets ---
MAX_COURTS = 4
try:
    ADMIN_PASSWORD = st.secrets.app_secrets.admin_password
    ADMIN_USERS = st.secrets.app_secrets.admin_users
except AttributeError:
    st.error("Your `secrets.toml` file is missing or misconfigured. It must contain admin_password and admin_users.")
    st.stop()

# --- Custom CSS for Accessibility & Style ---
st.markdown("""
<style>
    /* Base font size increase */
    html, body, .main, .stButton>button, .stTextInput input, .stSelectbox select {
        font-size: 18px !important;
    }
    .main .block-container{padding:1rem 1rem 10rem}
    [data-testid="stVerticalBlock"]>[data-testid="stVerticalBlock"]>[data-testid=stVerticalBlock]>[data-testid=stVerticalBlock]>div:nth-child(1)>div{border-radius:.75rem;box-shadow:0 4px 6px rgba(0,0,0,.05);border:1px solid #e6e6e6}
    
    /* Larger, bolder text elements */
    h1 { font-size: 2.5rem !important; font-weight: 700 !important; }
    h2, h3 { font-size: 2rem !important; font-weight: 600 !important; }
    h4 { font-size: 1.5rem !important; font-weight: 600 !important; margin-bottom: .5rem; }
    
    /* Enhanced Player Pills */
    .player-pill {
        display: block; padding: 12px 16px; margin: 6px 0; border-radius: 10px;
        background-color: #f0f2f6; font-weight: 600; border: 1px solid #ddd;
        font-size: 1.1rem;
    }
    .player-pill-chooser {
        background-color: #fff0c1; border: 2px solid #ffbf00; font-weight: 700;
    }

    /* Drag and Drop Containers */
    .dnd-container {
        border: 2px dashed #ccc;
        border-radius: 10px;
        padding: 10px;
        min-height: 100px;
        background-color: #fafafa;
    }
    .dnd-container h5 {
        font-size: 1.2rem;
        font-weight: 600;
        margin-bottom: 10px;
        color: #555;
    }
</style>
""", unsafe_allow_html=True)


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

# Persistent Player Data and Session-Specific Data
PLAYERS_COLLECTION_REF = db.collection("players") if db else None
SESSION_DOC_REF = db.collection("session").document("live_state") if db else None
LOG_COLLECTION_REF = db.collection("session").document("live_state").collection("game_log") if db else None

@st.cache_data(ttl=60)
def get_players_db():
    if not PLAYERS_COLLECTION_REF: return {}
    docs = PLAYERS_COLLECTION_REF.stream()
    return {doc.id: doc.to_dict() for doc in docs}

def get_live_state():
    if not SESSION_DOC_REF: return {}
    doc = SESSION_DOC_REF.get()
    if doc.exists:
        state = doc.to_dict()
        # Ensure queue keys exist
        if 'finishers_queue' not in state: state['finishers_queue'] = []
        if 'main_queue' not in state: state['main_queue'] = []
        return state
    else:
        # Default state for a new session
        default_state = {
            'attendees': [], 'finishers_queue': [], 'main_queue': [], 'active_games': {},
            'session_password': generate_password(), 'last_chooser_id': None
        }
        SESSION_DOC_REF.set(default_state)
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
        st.write("### Log in with your **Name** to mark your attendance.")

        with st.form("player_login_form"):
            typed_name = st.text_input("Enter your full name")
            session_password = st.text_input("Today's Session Password", type="password")
            submitted = st.form_submit_button("Mark My Attendance")

            if submitted:
                if not typed_name:
                    st.error("Please enter your name.")
                elif session_password != live_state.get('session_password'):
                    st.error("Incorrect session password.")
                else:
                    standardized_name = typed_name.strip().title()
                    # Find player by name in the persistent database
                    found_player_id, found_player = next(((pid, p) for pid, p in players_db.items() if p.get('name', '').lower() == standardized_name.lower()), (None, None))

                    if not found_player:
                        with st.spinner(f"Welcome, {standardized_name}! Creating your player profile..."):
                            # Create a new persistent player profile
                            found_player_id = "".join(random.choices(string.ascii_letters + string.digits, k=20))
                            found_player = {
                                'name': standardized_name,
                                'gender': "Men",  # Default or ask
                                'skill': 2,
                                'chooser_count': 0,
                                'games_played': 0,
                                'wins': 0
                            }
                            PLAYERS_COLLECTION_REF.document(found_player_id).set(found_player)
                            st.cache_data.clear()  # Clear cache to fetch new player

                    # Mark player as present for the session
                    player_id_str = str(found_player_id)
                    if player_id_str not in live_state.get('attendees', []):
                        SESSION_DOC_REF.update({
                            'attendees': firestore.ArrayUnion([player_id_str]),
                            'main_queue': firestore.ArrayUnion([player_id_str])
                        })

                    st.session_state.player_logged_in_name = found_player['name']
                    cookie_manager.set('player_name', found_player['name'], expires_at=datetime.datetime.now() + timedelta(hours=3))
                    st.toast(f"Welcome, {found_player['name']}! You're checked in.", icon="✅")
                    st.rerun()

    else:
        st.title(f"✅ Attendance Marked, {st.session_state.player_logged_in_name}!")
        st.subheader("Current Waiting Queue")

        waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
        waiting_players = get_players_from_ids(waiting_pids, players_db)

        if not waiting_players:
            st.info("The waiting list is empty.")
        else:
            pills = [
                f"<div class='player-pill' style='{'background-color: #d0eaff; border: 2px solid #006aff;' if p and p['name'] == st.session_state.player_logged_in_name else ''}'>"
                f"{i+1}. {p['name'] if p else '...'}</div>"
                for i, p in enumerate(waiting_players)
            ]
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
        with st.expander("### Admin Tools"):
            admin_pw = st.text_input("Enter Admin Password", type="password", key="court_admin_pw_check")
            if st.button("Show Session Password"):
                if admin_pw == ADMIN_PASSWORD: st.success(f"Password is: **{live_state.get('session_password')}**")
                else: st.error("Incorrect Admin Password.")
        return
    render_sidebar(live_state, players_db, cookie_manager)
    render_main_dashboard(live_state, players_db)
    st_autorefresh(interval=5000, key="court_refresher")


def get_players_from_ids(pids: List[str], players_db: dict) -> List[dict]:
    return [players_db.get(pid) for pid in pids if pid in players_db]


def clear_session_data():
    if SESSION_DOC_REF:
        SESSION_DOC_REF.set({
            'attendees': [], 'finishers_queue': [], 'main_queue': [], 'active_games': {},
            'session_password': generate_password(), 'last_chooser_id': None
        })
    if LOG_COLLECTION_REF:
        for doc in LOG_COLLECTION_REF.stream(): doc.reference.delete()


def render_sidebar(live_state, players_db, cookie_manager):
    with st.sidebar:
        st.title("🏸 Acers Club")
        st.markdown(f"### Operator: **{st.session_state.court_operator_logged_in}**")
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
            if st.button("🔄 Reset Current Session", use_container_width=True, type="secondary", help="Clears attendance, queues, and game logs, but keeps player profiles and stats."):
                clear_session_data()
                st.toast("Session has been reset!", icon="🧹")
                st.rerun()


def render_main_dashboard(live_state, players_db):
    courts_col, queue_col = st.columns([3, 1])
    with courts_col:
        tabs = st.tabs(["🏟️ Courts", "📊 Player Stats", "📋 Game Log", "👋 Check-out"])

        with tabs[0]:  # Courts Tab
            render_courts_view(live_state, players_db)

        with tabs[1]:  # Player Stats Tab
            render_player_stats(players_db)

        with tabs[2]:  # Game Log Tab
            render_game_log()

        with tabs[3]:  # Check-out Tab
            render_checkout_view(live_state, players_db)

    with queue_col:
        render_queue_view(live_state, players_db)


# --- Main Dashboard Tabs ---
def render_courts_view(live_state, players_db):
    st.header("Active Courts")
    court_grid_cols = st.columns(2)
    for i in range(MAX_COURTS):
        cid_str, game = str(i + 1), live_state.get('active_games', {}).get(str(i + 1))
        with court_grid_cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"<h4>Court {cid_str}</h4>", unsafe_allow_html=True)
                if game:
                    render_active_game(cid_str, game, players_db)
                else:
                    render_free_court(cid_str, live_state, players_db)


def render_player_stats(players_db):
    st.header("🏆 Player Statistics")
    if not players_db:
        st.info("No player data available yet.")
        return

    player_data = []
    for pid, p in players_db.items():
        games = p.get('games_played', 0)
        wins = p.get('wins', 0)
        win_rate = (wins / games * 100) if games > 0 else 0
        player_data.append({
            "Name": p['name'],
            "Games Played": games,
            "Wins": wins,
            "Win Rate (%)": f"{win_rate:.1f}"
        })

    st.subheader("Leaderboard")
    df = pd.DataFrame(player_data)
    # Ensure Win Rate is numeric for sorting
    df['Win Rate (%)'] = pd.to_numeric(df['Win Rate (%)'])
    df = df.sort_values(by="Win Rate (%)", ascending=False).reset_index(drop=True)
    st.dataframe(df, use_container_width=True, hide_index=True)


    st.subheader("🤝 Partnership Stats")
    log_docs = LOG_COLLECTION_REF.stream()
    wins = defaultdict(int)
    played = defaultdict(int)
    for doc in log_docs:
        log = doc.to_dict()
        t1_names = sorted(log.get('Team 1 Players', '').split(' & '))
        t2_names = sorted(log.get('Team 2 Players', '').split(' & '))
        if len(t1_names) == 2:
            pair = tuple(t1_names)
            played[pair] += 1
            if log.get('Winner') == 'Team 1': wins[pair] += 1
        if len(t2_names) == 2:
            pair = tuple(t2_names)
            played[pair] += 1
            if log.get('Winner') == 'Team 2': wins[pair] += 1

    partnership_data = []
    for pair, count in played.items():
        win_count = wins[pair]
        win_rate = (win_count / count * 100) if count > 0 else 0
        if count > 0: # Only show pairs that have played
            partnership_data.append({
                "Partners": f"{pair[0]} & {pair[1]}",
                "Games Together": count,
                "Wins": win_count,
                "Partnership Win Rate (%)": f"{win_rate:.1f}"
            })

    if partnership_data:
        df_partners = pd.DataFrame(partnership_data)
        df_partners['Partnership Win Rate (%)'] = pd.to_numeric(df_partners['Partnership Win Rate (%)'])
        df_partners = df_partners.sort_values(by="Games Together", ascending=False)
        st.dataframe(df_partners, use_container_width=True, hide_index=True)
    else:
        st.info("No partnership data yet. Play some games!")


def render_game_log():
    st.header("Completed Games Log")
    log_docs = LOG_COLLECTION_REF.order_by("finish_time", direction=firestore.Query.DESCENDING).stream()
    log_data = [doc.to_dict() for doc in log_docs]
    if not log_data: st.info("No games logged yet.")
    else:
        df = pd.DataFrame(log_data)
        df['finish_time'] = pd.to_datetime(df['finish_time']).dt.tz_convert('Europe/London').dt.strftime('%H:%M:%S')
        df.rename(columns={'finish_time': 'Finish Time'}, inplace=True)
        df = df[['Finish Time', 'Duration', 'Court', 'Team 1 Players', 'Team 2 Players', 'Score', 'Winner']]
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_checkout_view(live_state, players_db):
    st.header("Player Check-out")
    present_pids = live_state.get('attendees', [])
    present_players = get_players_from_ids(present_pids, players_db)
    if not present_players:
        st.info("No players are currently checked in.")
    else:
        names_to_check_out = st.multiselect("Select players to check out", [p['name'] for p in present_players if p])
        if st.button("Check Out Selected Players", disabled=not names_to_check_out):
            pids_to_remove = [pid for pid, p in players_db.items() if p and p['name'] in names_to_check_out]
            SESSION_DOC_REF.update({
                'attendees': firestore.ArrayRemove(pids_to_remove),
                'finishers_queue': firestore.ArrayRemove(pids_to_remove),
                'main_queue': firestore.ArrayRemove(pids_to_remove)
            })
            st.toast(f"Checked out {', '.join(names_to_check_out)}.", icon="👋"); st.rerun()


# --- Court View Components ---
def render_active_game(cid_str, game, players_db):
    team1_pids = game.get('team1_pids', []); team2_pids = game.get('team2_pids', [])
    team1_players = get_players_from_ids(team1_pids, players_db); team2_players = get_players_from_ids(team2_pids, players_db)
    st.markdown(f"**Team 1:** {' & '.join([p['name'] for p in team1_players if p])}")
    st.markdown(f"**Team 2:** {' & '.join([p['name'] for p in team2_players if p])}")

    start_time = game.get('start_time')
    if isinstance(start_time, str): start_time = datetime.datetime.fromisoformat(start_time).replace(tzinfo=timezone.utc)
    elif isinstance(start_time, datetime.datetime) and start_time.tzinfo is None: start_time = start_time.replace(tzinfo=timezone.utc)
    
    if not start_time: start_time = datetime.datetime.now(timezone.utc)

    elapsed = datetime.datetime.now(timezone.utc) - start_time
    st.metric("Time Elapsed", f"{int(elapsed.total_seconds() // 60):02d}:{int(elapsed.total_seconds() % 60):02d}")


    s_cols = st.columns(2)
    t1s, t2s = s_cols[0].number_input("T1 Score", 0, 30, step=1, key=f"t1s_{cid_str}"), s_cols[1].number_input("T2 Score", 0, 30, step=1, key=f"t2s_{cid_str}")

    if st.button("Log Score & Finish", key=f"log_{cid_str}", use_container_width=True, type="primary"):
        # Determine winners and losers
        winning_pids = team1_pids if t1s > t2s else team2_pids
        losing_pids = team2_pids if t1s > t2s else team1_pids
        is_draw = t1s == t2s
        if is_draw: winning_pids, losing_pids = [], team1_pids + team2_pids

        # Order winners by chooser count for fairness
        winners = get_players_from_ids(winning_pids, players_db)
        if len(winners) == 2:
            p1_id = next(pid for pid, p in players_db.items() if p['name'] == winners[0]['name'])
            p2_id = next(pid for pid, p in players_db.items() if p['name'] == winners[1]['name'])
            p1_count = winners[0].get('chooser_count', 0)
            p2_count = winners[1].get('chooser_count', 0)
            ordered_winners = [p1_id, p2_id] if p1_count <= p2_count else [p2_id, p1_id]
        else:
             ordered_winners = winning_pids

        new_finishers = ordered_winners + losing_pids

        # Update session state
        live_state['active_games'].pop(cid_str)
        SESSION_DOC_REF.update({
            'active_games': live_state['active_games'],
            'finishers_queue': firestore.ArrayUnion(new_finishers)
        })

        # Update player profiles (stats)
        batch = db.batch()
        for pid in winning_pids:
            ref = PLAYERS_COLLECTION_REF.document(str(pid))
            batch.update(ref, {'games_played': firestore.Increment(1), 'wins': firestore.Increment(1)})
        for pid in losing_pids:
            ref = PLAYERS_COLLECTION_REF.document(str(pid))
            batch.update(ref, {'games_played': firestore.Increment(1)})
        if ordered_winners:
            chooser_ref = PLAYERS_COLLECTION_REF.document(str(ordered_winners[0]))
            batch.update(chooser_ref, {'chooser_count': firestore.Increment(1)})
        batch.commit()

        # Log the game
        log = {'finish_time': firestore.SERVER_TIMESTAMP, 'Duration': f"{int(elapsed.total_seconds() // 60)}m", 'Court': cid_str,
               'Team 1 Players': " & ".join([p['name'] for p in team1_players if p]), 'Team 2 Players': " & ".join([p['name'] for p in team2_players if p]),
               'Score': f"{t1s} - {t2s}", 'Winner': "Draw" if is_draw else "Team 1" if t1s > t2s else "Team 2"}
        LOG_COLLECTION_REF.add(log)
        st.cache_data.clear()  # Clear cache to refetch player stats
        st.rerun()


def render_free_court(cid_str, live_state, players_db):
    waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
    if len(waiting_pids) < 4:
        st.info("Court available. Need at least 4 players waiting.")
    else:
        chooser_pid = waiting_pids[0]
        chooser_player = players_db.get(chooser_pid)
        if not chooser_player: st.error("Chooser not found!"); return

        st.success(f"👑 **{chooser_player.get('name', 'N/A')}** is choosing.")

        available_pids = waiting_pids[1:]

        # Initialize session state for dnd lists if not present
        dnd_keys = [f'game_players_{cid_str}', f'team1_{cid_str}', f'team2_{cid_str}', f'unassigned_{cid_str}']
        for key in dnd_keys:
            if key not in st.session_state:
                st.session_state[key] = []
        
        # --- Drag and Drop UI ---
        # Box to select the 3 other players
        st.markdown("<h5>1. Available Players (Drag 3 to the box below)</h5>", unsafe_allow_html=True)
        available_list = [p['name'] for p in get_players_from_ids(available_pids, players_db) if p['name'] not in st.session_state[f'game_players_{cid_str}']]
        game_players_box = st_dnd(id=f'dnd_select_{cid_str}', items=available_list, box_style="dnd-container")
        
        # Update session state when 3 players are selected
        if game_players_box is not None and len(game_players_box) == 3:
            st.session_state[f'game_players_{cid_str}'] = game_players_box
            all_four_players = [chooser_player['name']] + game_players_box
            st.session_state[f'unassigned_{cid_str}'] = all_four_players
            st.rerun() # Rerun to move to team selection phase
        
        # Once 3 players are chosen, show team selection boxes
        if len(st.session_state[f'game_players_{cid_str}']) == 3:
            st.markdown("---")
            st.markdown(f"**Game Players:** {chooser_player['name']}, {', '.join(st.session_state[f'game_players_{cid_str}'])}")
            
            st.markdown("<h5>2. Unassigned (Drag to teams)</h5>", unsafe_allow_html=True)
            unassigned_result = st_dnd(id=f'dnd_unassigned_{cid_str}', items=st.session_state[f'unassigned_{cid_str}'], box_style="dnd-container")

            t1_col, t2_col = st.columns(2)
            with t1_col:
                st.markdown("<h5>Team 1</h5>", unsafe_allow_html=True)
                team1_result = st_dnd(id=f'dnd_t1_{cid_str}', items=st.session_state[f'team1_{cid_str}'], box_style="dnd-container")
            with t2_col:
                st.markdown("<h5>Team 2</h5>", unsafe_allow_html=True)
                team2_result = st_dnd(id=f'dnd_t2_{cid_str}', items=st.session_state[f'team2_{cid_str}'], box_style="dnd-container")
            
            # Sync state after any DND operation
            if (st.session_state[f'unassigned_{cid_str}'] != unassigned_result or
                st.session_state[f'team1_{cid_str}'] != team1_result or
                st.session_state[f'team2_{cid_str}'] != team2_result):
                
                st.session_state[f'unassigned_{cid_str}'] = unassigned_result
                st.session_state[f'team1_{cid_str}'] = team1_result
                st.session_state[f'team2_{cid_str}'] = team2_result
                st.rerun()

            if len(team1_result) == 2 and len(team2_result) == 2:
                if st.button("Start Game", key=f"start_dnd_{cid_str}", use_container_width=True, type="primary"):
                    team1_pids = [pid for pid, p in players_db.items() if p['name'] in team1_result]
                    team2_pids = [pid for pid, p in players_db.items() if p['name'] in team2_result]
                    all_pids = team1_pids + team2_pids
                    
                    live_state['active_games'][cid_str] = {
                        'team1_pids': team1_pids,
                        'team2_pids': team2_pids,
                        'player_ids': all_pids,
                        'start_time': firestore.SERVER_TIMESTAMP
                    }
                    
                    SESSION_DOC_REF.update({
                        'finishers_queue': firestore.ArrayRemove(all_pids),
                        'main_queue': firestore.ArrayRemove(all_pids),
                        'active_games': live_state['active_games']
                    })
                    
                    # Clear dnd state for this court and rerun
                    for key in dnd_keys:
                        if key in st.session_state: del st.session_state[key]
                    st.rerun()


def render_queue_view(live_state, players_db):
    st.header("⏳ Waiting Queue")
    st.caption("Finishers move to the top, winners first.")
    waiting_pids = live_state.get('finishers_queue', []) + live_state.get('main_queue', [])
    waiting_players = get_players_from_ids(waiting_pids, players_db)

    if not waiting_players:
        st.info("Waiting list is empty.")
    else:
        for i, p in enumerate(waiting_players):
            if p:
                is_chooser = (i == 0)
                icon = "👑 " if is_chooser else ""
                st.markdown(f"<div class='player-pill {'player-pill-chooser' if is_chooser else ''}'>{i+1}. {icon}{p['name']}</div>", unsafe_allow_html=True)

    if st.session_state.court_operator_logged_in in ADMIN_USERS:
        with st.expander("### Remove Player from Queue"):
            if waiting_players:
                names_to_remove = st.multiselect("Select players to remove", [p['name'] for p in waiting_players if p])
                if st.button("Remove Selected", disabled=not names_to_remove):
                    pids_to_remove = [pid for pid, p in players_db.items() if p and p['name'] in names_to_remove]
                    SESSION_DOC_REF.update({
                        'finishers_queue': firestore.ArrayRemove(pids_to_remove),
                        'main_queue': firestore.ArrayRemove(pids_to_remove)
                    })
                    st.toast(f"Removed {', '.join(names_to_remove)}.", icon="👋"); st.rerun()
            else:
                st.write("Queue is empty.")


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
