import streamlit as st
import time
import random
import datetime
import itertools
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
from streamlit_autorefresh import st_autorefresh

# --- App Configuration ---
st.set_page_config(page_title="Badminton Scheduler", layout="wide")

# --- Firebase Initialization ---
def init_firebase():
    """Initialize Firebase connection using Streamlit secrets."""
    try:
        # Check if the app is already initialized
        if not firebase_admin._apps:
            cred = credentials.Certificate(dict(st.secrets["firebase_credentials"]))
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception as e:
        st.error(f"Failed to initialize Firebase. Please check your secrets.toml file. Error: {e}")
        return None

db = init_firebase()

# --- Constants & State Handling ---
# We now use a single document in Firestore to hold the entire session state.
SESSION_DOC_REF = db.collection("session").document("current_state") if db else None

def get_session_state():
    """Fetch the current session state from Firestore."""
    if not SESSION_DOC_REF: return {}
    doc = SESSION_DOC_REF.get()
    if doc.exists:
        return doc.to_dict()
    else:
        # If no state exists, create a default one
        default_state = {
            'all_players': [], 'session_started': False, 'attendees': {},
            'waiting_players': [], 'active_games': [], 'player_history': {},
            'game_stats': []
        }
        SESSION_DOC_REF.set(default_state)
        return default_state

def set_session_state(state):
    """Update the session state in Firestore."""
    if SESSION_DOC_REF:
        SESSION_DOC_REF.set(state)

# Load state at the beginning of the script run
if db:
    st.session_state.app_state = get_session_state()
else:
    st.session_state.app_state = {}


MAX_COURTS = 4
SKILL_MAP = {1: 'Beginner', 2: 'Intermediate', 3: 'Advanced'}


# --- Sidebar for Player Management ---
with st.sidebar:
    st.header("Player Roster")
    with st.form("add_player_form", clear_on_submit=True):
        new_player_name = st.text_input("Player Name")
        new_player_skill = st.selectbox("Skill Level", options=list(SKILL_MAP.keys()), format_func=lambda x: SKILL_MAP[x], index=1)
        if st.form_submit_button("Add Player"):
            if new_player_name:
                player_id = int(time.time() * 1000)
                new_player = {'id': player_id, 'name': new_player_name, 'skill': new_player_skill}
                st.session_state.app_state['all_players'].append(new_player)
                set_session_state(st.session_state.app_state)
                st.success(f"Added {new_player_name}")
                st.rerun()

    st.subheader("Current Players")
    if not st.session_state.app_state.get('all_players'):
        st.info("No players added yet.")
    else:
        sorted_players = sorted(st.session_state.app_state['all_players'], key=lambda p: p['name'])
        for player in sorted_players:
            col1, col2, col3 = st.columns([3, 2, 1])
            col1.write(f"**{player['name']}**")
            col2.write(f"_{SKILL_MAP[player['skill']]}_")
            if col3.button("❌", key=f"del_{player['id']}", help=f"Remove {player['name']}"):
                st.session_state.app_state['all_players'] = [p for p in st.session_state.app_state['all_players'] if p['id'] != player['id']]
                set_session_state(st.session_state.app_state)
                st.rerun()

# --- Main Content Area ---
st.title("🏸 Badminton Score & Scheduler")

if not st.session_state.app_state.get('session_started'):
    st.header("1. Mark Attendance")
    all_players = st.session_state.app_state.get('all_players', [])
    if not all_players:
        st.warning("Please add players to the roster using the sidebar.")
    else:
        attendee_selections = {p['id']: st.checkbox(f"{p['name']} ({SKILL_MAP[p['skill']]})", key=f"att_{p['id']}") for p in sorted(all_players, key=lambda p: p['name'])}
        num_attendees = sum(attendee_selections.values())
        st.info(f"**{num_attendees}** players selected.")
        if st.button("Start Session", disabled=(num_attendees < 4), type="primary", use_container_width=True):
            st.session_state.app_state['attendees'] = {str(p['id']): p for p in all_players if attendee_selections.get(p['id'])}
            st.session_state.app_state['waiting_players'] = list(st.session_state.app_state['attendees'].values())
            st.session_state.app_state['player_history'] = {str(pid): {'with': [], 'against': []} for pid in st.session_state.app_state['attendees']}
            st.session_state.app_state['session_started'] = True
            set_session_state(st.session_state.app_state)
            st.rerun()
else: # Session is active
    # --- Matchmaking Logic ---
    def find_best_match(available_players, history):
        best_match, max_variety_score = None, -1
        for combo in itertools.combinations(available_players, 4):
            variety_score = 0
            for i, p1 in enumerate(combo):
                p1_hist = history.get(str(p1['id']), {'with': [], 'against': []})
                for j, p2 in enumerate(combo):
                    if i == j: continue
                    if p2['id'] not in p1_hist['with']: variety_score += 1
                    if p2['id'] not in p1_hist['against']: variety_score += 1
            if variety_score > max_variety_score:
                max_variety_score, best_match = variety_score, list(combo)
        return best_match

    def create_new_games():
        state = st.session_state.app_state
        made_change = False
        while len(state['waiting_players']) >= 4 and len(state['active_games']) < MAX_COURTS:
            made_change = True
            game_players = find_best_match(state['waiting_players'], state['player_history'])
            if not game_players: break
            state['waiting_players'] = [p for p in state['waiting_players'] if p not in game_players]
            game_players.sort(key=lambda p: p['skill'], reverse=True)
            team1, team2 = [game_players[0], game_players[3]], [game_players[1], game_players[2]]
            
            for p in team1:
                p_id_str = str(p['id'])
                state['player_history'][p_id_str]['with'].append(team1[1-team1.index(p)]['id'])
                state['player_history'][p_id_str]['against'].extend([p2['id'] for p2 in team2])
            for p in team2:
                p_id_str = str(p['id'])
                state['player_history'][p_id_str]['with'].append(team2[1-team2.index(p)]['id'])
                state['player_history'][p_id_str]['against'].extend([p1['id'] for p1 in team1])

            used_court_ids = {g['court_id'] for g in state['active_games']}
            next_court_id = next(i for i in range(1, MAX_COURTS + 2) if i not in used_court_ids)
            state['active_games'].append({'court_id': next_court_id, 'team1': team1, 'team2': team2})
        
        if made_change:
            set_session_state(state)
            st.rerun()

    # --- Main Display Logic ---
    st.header("Session Status")
    create_new_games()

    st.subheader("Waiting for Next Game")
    waiting_players = st.session_state.app_state.get('waiting_players', [])
    if not waiting_players: st.info("No players are waiting.")
    else: st.write(" | ".join([f"{p['name']} ({SKILL_MAP[p['skill']]})" for p in waiting_players]))
    
    st.divider()
    st.header("Active Courts")
    active_games = st.session_state.app_state.get('active_games', [])
    if not active_games: st.success("All courts are free!")
    else:
        cols = st.columns(MAX_COURTS)
        for i, game in enumerate(sorted(active_games, key=lambda g: g['court_id'])):
            with cols[i % MAX_COURTS]:
                with st.container(border=True):
                    st.subheader(f"Court {game['court_id']}")
                    t1n, t2n = f"{game['team1'][0]['name']} & {game['team1'][1]['name']}", f"{game['team2'][0]['name']} & {game['team2'][1]['name']}"
                    st.markdown(f"**{t1n}** vs **{t2n}**")
                    s_col1, s_col2 = st.columns(2)
                    score1 = s_col1.number_input("Team 1 Score", 0, 30, key=f"s1_{game['court_id']}")
                    score2 = s_col2.number_input("Team 2 Score", 0, 30, key=f"s2_{game['court_id']}")
                    if st.button("Finish Game", key=f"fin_{game['court_id']}", use_container_width=True):
                        state = st.session_state.app_state
                        state['game_stats'].append({"court": game['court_id'], "team1": t1n, "team2": t2n, "score": f"{score1}-{score2}", "timestamp": datetime.datetime.now().isoformat()})
                        state['waiting_players'].extend(game['team1'])
                        state['waiting_players'].extend(game['team2'])
                        state['active_games'] = [g for g in state['active_games'] if g['court_id'] != game['court_id']]
                        set_session_state(state)
                        st.rerun()
    
    st.divider()
    with st.expander("Show Completed Games Log"):
        game_stats = st.session_state.app_state.get('game_stats', [])
        if not game_stats: st.info("No games have been completed yet.")
        else:
            df = pd.DataFrame(reversed(game_stats))
            df['timestamp'] = pd.to_datetime(df['timestamp']).dt.strftime('%H:%M:%S')
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("Export to CSV", data=csv, file_name='badminton_session_stats.csv', mime='text/csv')

    if st.button("End Session", type="primary"):
        # Reset the state in Firestore
        SESSION_DOC_REF.set({
            'all_players': st.session_state.app_state.get('all_players', []), # Keep the roster
            'session_started': False, 'attendees': {}, 'waiting_players': [], 
            'active_games': [], 'player_history': {}, 'game_stats': []
        })
        st.rerun()

# This will auto-refresh the page every 5 seconds to sync state from Firestore
st_autorefresh(interval=5000, key="state_refresher")
