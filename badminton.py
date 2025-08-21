import streamlit as st
import time
import random
import datetime

# --- App Configuration ---
st.set_page_config(page_title="Badminton Scheduler", layout="wide")

# --- Constants ---
MAX_COURTS = 4
SKILL_MAP = {1: 'Beginner', 2: 'Intermediate', 3: 'Advanced'}
MIN_GAME_MINUTES = 3
MAX_GAME_MINUTES = 10
SESSION_DURATION_HOURS = 2

# --- Helper Functions ---
def initialize_state():
    """Initializes the session state variables if they don't exist."""
    if 'all_players' not in st.session_state:
        st.session_state.all_players = [] # List of {'id': int, 'name': str, 'skill': int}
    if 'session_started' not in st.session_state:
        st.session_state.session_started = False
    if 'attendees' not in st.session_state:
        st.session_state.attendees = {} # Dict of {player_id: player_data}
    if 'waiting_players' not in st.session_state:
        st.session_state.waiting_players = []
    if 'active_games' not in st.session_state:
        st.session_state.active_games = [] # List of game dicts
    if 'is_auto_mode' not in st.session_state:
        st.session_state.is_auto_mode = False
    if 'session_end_time' not in st.session_state:
        st.session_state.session_end_time = None

def format_time_delta(delta):
    """Formats a timedelta object into H:M:S or M:S string."""
    total_seconds = int(delta.total_seconds())
    if total_seconds < 0:
        return "Finished!"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours > 0:
        return f"{hours:02}:{minutes:02}:{seconds:02}"
    return f"{minutes:02}:{seconds:02}"

# --- Main App Logic ---
initialize_state()

# --- Sidebar for Player Management ---
with st.sidebar:
    st.header("Player Roster")
    with st.form("add_player_form", clear_on_submit=True):
        new_player_name = st.text_input("Player Name", key="new_player_name")
        new_player_skill = st.selectbox(
            "Skill Level",
            options=list(SKILL_MAP.keys()),
            format_func=lambda x: SKILL_MAP[x],
            index=1
        )
        submitted = st.form_submit_button("Add Player")
        if submitted and new_player_name:
            player_id = int(time.time() * 1000)
            st.session_state.all_players.append({
                'id': player_id,
                'name': new_player_name,
                'skill': new_player_skill
            })
            st.success(f"Added {new_player_name}")

    st.subheader("Current Players")
    if not st.session_state.all_players:
        st.info("No players added yet.")
    else:
        # Sort players for consistent display
        sorted_players = sorted(st.session_state.all_players, key=lambda p: p['name'])
        for i, player in enumerate(sorted_players):
            col1, col2, col3 = st.columns([3, 2, 1])
            with col1:
                st.write(f"**{player['name']}**")
            with col2:
                st.write(f"_{SKILL_MAP[player['skill']]}_")
            with col3:
                if st.button("❌", key=f"del_{player['id']}", help=f"Remove {player['name']}"):
                    st.session_state.all_players = [p for p in st.session_state.all_players if p['id'] != player['id']]
                    st.rerun()


# --- Main Content Area ---
st.title("🏸 Badminton Session Scheduler")

if not st.session_state.session_started:
    st.header("1. Mark Attendance")
    if not st.session_state.all_players:
        st.warning("Please add players to the roster using the sidebar.")
    else:
        attendee_selections = {}
        sorted_players = sorted(st.session_state.all_players, key=lambda p: p['name'])
        for player in sorted_players:
            attendee_selections[player['id']] = st.checkbox(
                f"{player['name']} ({SKILL_MAP[player['skill']]})",
                key=f"att_{player['id']}"
            )

        num_attendees = sum(attendee_selections.values())
        st.info(f"**{num_attendees}** players selected.")

        can_start = num_attendees >= 4
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Start Manual Session", disabled=not can_start, use_container_width=True):
                st.session_state.attendees = {
                    p['id']: p for p in st.session_state.all_players if attendee_selections.get(p['id'])
                }
                st.session_state.waiting_players = list(st.session_state.attendees.values())
                st.session_state.session_started = True
                st.session_state.is_auto_mode = False
                st.rerun()
        with col2:
            if st.button(f"Start {SESSION_DURATION_HOURS}-Hour Auto-Session", disabled=not can_start, type="primary", use_container_width=True):
                st.session_state.attendees = {
                    p['id']: p for p in st.session_state.all_players if attendee_selections.get(p['id'])
                }
                st.session_state.waiting_players = list(st.session_state.attendees.values())
                st.session_state.session_started = True
                st.session_state.is_auto_mode = True
                st.session_state.session_end_time = datetime.datetime.now() + datetime.timedelta(hours=SESSION_DURATION_HOURS)
                st.rerun()

else: # Session is active
    # --- Session Status and Controls ---
    st.header("Session Status")
    
    # Check for finished games and session end
    now = datetime.datetime.now()
    games_to_finish = [game for game in st.session_state.active_games if now >= game['end_time']]
    
    if games_to_finish:
        for game in games_to_finish:
            st.session_state.waiting_players.extend(game['team1'])
            st.session_state.waiting_players.extend(game['team2'])
        st.session_state.active_games = [g for g in st.session_state.active_games if g not in games_to_finish]
        st.toast("A game has finished! Players are back in the waiting pool.")

    if st.session_state.session_end_time and now >= st.session_state.session_end_time:
        st.success("Session finished!")
        for key in ['session_started', 'is_auto_mode', 'session_end_time', 'active_games', 'waiting_players', 'attendees']:
            st.session_state[key] = None if key == 'session_end_time' else (False if isinstance(st.session_state[key], bool) else [])
        time.sleep(2)
        st.rerun()

    # Auto-generate game in auto mode
    if st.session_state.is_auto_mode and len(st.session_state.waiting_players) >= 4 and len(st.session_state.active_games) < MAX_COURTS:
        # This block will attempt to create a game on every rerun if conditions are met
        shuffled = random.sample(st.session_state.waiting_players, len(st.session_state.waiting_players))
        game_players = shuffled[:4]
        game_players.sort(key=lambda p: p['skill'], reverse=True)
        
        team1 = [game_players[0], game_players[3]]
        team2 = [game_players[1], game_players[2]]
        
        st.session_state.waiting_players = [p for p in st.session_state.waiting_players if p not in game_players]
        
        used_court_ids = {g['court_id'] for g in st.session_state.active_games}
        next_court_id = next(i for i in range(1, MAX_COURTS + 1) if i not in used_court_ids)
        
        duration = random.randint(MIN_GAME_MINUTES, MAX_GAME_MINUTES)
        end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration)
        
        st.session_state.active_games.append({
            'court_id': next_court_id,
            'team1': team1,
            'team2': team2,
            'end_time': end_time
        })
        st.toast(f"Auto-generated a new game on Court {next_court_id}!")


    # Display Session Info
    mode = "Auto-Pilot" if st.session_state.is_auto_mode else "Manual"
    st.subheader(f"Mode: {mode}")
    if st.session_state.session_end_time:
        time_left = st.session_state.session_end_time - now
        st.metric("Session Time Remaining", format_time_delta(time_left))

    # --- Waiting Players and Manual Generation ---
    st.header("2. Waiting Players")
    if not st.session_state.waiting_players:
        st.info("No players are currently waiting.")
    else:
        sorted_waiting = sorted(st.session_state.waiting_players, key=lambda p: p['skill'], reverse=True)
        player_tags = [f"{p['name']} ({SKILL_MAP[p['skill']]})" for p in sorted_waiting]
        st.write(" | ".join(player_tags))

    can_generate = len(st.session_state.waiting_players) >= 4 and len(st.session_state.active_games) < MAX_COURTS
    if st.button("Generate Balanced Game", disabled=not can_generate):
        # Manual game generation logic (same as auto)
        shuffled = random.sample(st.session_state.waiting_players, len(st.session_state.waiting_players))
        game_players = shuffled[:4]
        game_players.sort(key=lambda p: p['skill'], reverse=True)
        team1, team2 = [game_players[0], game_players[3]], [game_players[1], game_players[2]]
        st.session_state.waiting_players = [p for p in st.session_state.waiting_players if p not in game_players]
        used_court_ids = {g['court_id'] for g in st.session_state.active_games}
        next_court_id = next(i for i in range(1, MAX_COURTS + 1) if i not in used_court_ids)
        duration = random.randint(MIN_GAME_MINUTES, MAX_GAME_MINUTES)
        end_time = datetime.datetime.now() + datetime.timedelta(minutes=duration)
        st.session_state.active_games.append({'court_id': next_court_id, 'team1': team1, 'team2': team2, 'end_time': end_time})
        st.rerun()

    # --- Active Courts ---
    st.header("3. Active Courts")
    if not st.session_state.active_games:
        st.info("All courts are free.")
    else:
        sorted_games = sorted(st.session_state.active_games, key=lambda g: g['court_id'])
        cols = st.columns(MAX_COURTS)
        for i, game in enumerate(sorted_games):
            with cols[i % MAX_COURTS]:
                with st.container(border=True):
                    st.subheader(f"Court {game['court_id']}")
                    team1_names = f"{game['team1'][0]['name']} & {game['team1'][1]['name']}"
                    team2_names = f"{game['team2'][0]['name']} & {game['team2'][1]['name']}"
                    st.markdown(f"**{team1_names}** vs **{team2_names}**")
                    time_left = game['end_time'] - now
                    st.metric("Time Left", format_time_delta(time_left))

    # --- Session Controls ---
    st.divider()
    col1, col2 = st.columns([1,5])
    with col1:
        if st.button("End Session", type="primary"):
            # Reset all session-related state
            for key in ['session_started', 'is_auto_mode', 'session_end_time', 'active_games', 'waiting_players', 'attendees']:
                 st.session_state[key] = None if key == 'session_end_time' else (False if isinstance(st.session_state[key], bool) else [])
            st.rerun()
    with col2:
        st.button("Refresh Status", on_click=st.rerun) # Force a rerun to update timers
