import streamlit as st
import time
import random
import datetime
import itertools

# --- App Configuration ---
st.set_page_config(page_title="Badminton Scheduler", layout="wide")

# --- Constants ---
MAX_COURTS = 4
SKILL_MAP = {1: 'Beginner', 2: 'Intermediate', 3: 'Advanced'}

# --- Helper Functions ---
def initialize_state():
    """Initializes the session state variables if they don't exist."""
    if 'all_players' not in st.session_state:
        st.session_state.all_players = []
    if 'session_started' not in st.session_state:
        st.session_state.session_started = False
    if 'attendees' not in st.session_state:
        st.session_state.attendees = {}
    if 'waiting_players' not in st.session_state:
        st.session_state.waiting_players = []
    if 'active_games' not in st.session_state:
        st.session_state.active_games = []
    if 'player_history' not in st.session_state:
        # Tracks who played with/against whom
        # {'player_id': {'with': {id1, id2}, 'against': {id3, id4}}}
        st.session_state.player_history = {}
    if 'game_stats' not in st.session_state:
        # List to store completed game statistics
        st.session_state.game_stats = []


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
        sorted_players = sorted(st.session_state.all_players, key=lambda p: p['name'])
        for player in sorted_players:
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
st.title("🏸 Badminton Score & Scheduler")

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

        if st.button("Start Session", disabled=(num_attendees < 4), type="primary", use_container_width=True):
            st.session_state.attendees = {
                p['id']: p for p in st.session_state.all_players if attendee_selections.get(p['id'])
            }
            st.session_state.waiting_players = list(st.session_state.attendees.values())
            # Initialize history for attendees
            for player_id in st.session_state.attendees:
                if player_id not in st.session_state.player_history:
                    st.session_state.player_history[player_id] = {'with': set(), 'against': set()}
            st.session_state.session_started = True
            st.rerun()

else: # Session is active
    # --- Matchmaking Logic ---
    def find_best_match(available_players):
        best_match = None
        max_variety_score = -1

        # Find all combinations of 4 players from the waiting pool
        for combo in itertools.combinations(available_players, 4):
            variety_score = 0
            # For each player, check novelty against the other 3
            for i, p1 in enumerate(combo):
                p1_history = st.session_state.player_history.get(p1['id'], {'with': set(), 'against': set()})
                for j, p2 in enumerate(combo):
                    if i == j: continue
                    # Higher score for playing with/against someone new
                    if p2['id'] not in p1_history['with']:
                        variety_score += 1
                    if p2['id'] not in p1_history['against']:
                        variety_score += 1
            
            if variety_score > max_variety_score:
                max_variety_score = variety_score
                best_match = list(combo)
        
        return best_match

    def create_new_games():
        """Continuously create games as long as courts and players are available."""
        while len(st.session_state.waiting_players) >= 4 and len(st.session_state.active_games) < MAX_COURTS:
            
            game_players = find_best_match(st.session_state.waiting_players)
            if not game_players: break # Should not happen if len >= 4

            # Remove chosen players from waiting list
            st.session_state.waiting_players = [p for p in st.session_state.waiting_players if p not in game_players]

            # Balance teams based on skill
            game_players.sort(key=lambda p: p['skill'], reverse=True)
            team1 = [game_players[0], game_players[3]]
            team2 = [game_players[1], game_players[2]]

            # Update player history
            for p in team1:
                st.session_state.player_history[p['id']]['with'].add(team1[1-team1.index(p)]['id'])
                st.session_state.player_history[p['id']]['against'].update([p2['id'] for p2 in team2])
            for p in team2:
                st.session_state.player_history[p['id']]['with'].add(team2[1-team2.index(p)]['id'])
                st.session_state.player_history[p['id']]['against'].update([p1['id'] for p1 in team1])

            used_court_ids = {g['court_id'] for g in st.session_state.active_games}
            next_court_id = next(i for i in range(1, MAX_COURTS + 2) if i not in used_court_ids)

            st.session_state.active_games.append({
                'court_id': next_court_id,
                'team1': team1,
                'team2': team2,
            })

    # --- Main Display Logic ---
    st.header("Session Status")
    
    # Try to create new games on every run
    create_new_games()

    # --- Player Pools Display ---
    st.subheader("Waiting for Next Game")
    if not st.session_state.waiting_players:
        st.info("No players are waiting.")
    else:
        player_tags = [f"{p['name']} ({SKILL_MAP[p['skill']]})" for p in st.session_state.waiting_players]
        st.write(" | ".join(player_tags))
    
    st.divider()

    # --- Active Courts Display ---
    st.header("Active Courts")
    if not st.session_state.active_games:
        st.success("All courts are free!")
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
                    
                    score_col1, score_col2 = st.columns(2)
                    with score_col1:
                        score1 = st.number_input("Team 1 Score", min_value=0, max_value=30, key=f"s1_{game['court_id']}")
                    with score_col2:
                        score2 = st.number_input("Team 2 Score", min_value=0, max_value=30, key=f"s2_{game['court_id']}")
                    
                    if st.button("Finish Game & Submit Score", key=f"fin_{game['court_id']}", use_container_width=True):
                        # Log game stats before removing
                        st.session_state.game_stats.append({
                            "court": game['court_id'],
                            "team1": team1_names,
                            "team2": team2_names,
                            "score": f"{score1} - {score2}",
                            "timestamp": datetime.datetime.now()
                        })

                        # Move players back to the waiting pool
                        st.session_state.waiting_players.extend(game['team1'])
                        st.session_state.waiting_players.extend(game['team2'])
                        
                        # Remove game from active list
                        st.session_state.active_games = [g for g in st.session_state.active_games if g['court_id'] != game['court_id']]
                        st.rerun()
    
    st.divider()

    # --- Completed Games Display ---
    with st.expander("Show Completed Games Log"):
        if not st.session_state.game_stats:
            st.info("No games have been completed yet.")
        else:
            # Display stats in reverse chronological order
            for stat in reversed(st.session_state.game_stats):
                st.markdown(
                    f"**Court {stat['court']}** ({stat['timestamp'].strftime('%H:%M:%S')}): "
                    f"{stat['team1']} vs {stat['team2']}  -  **Score: {stat['score']}**"
                )
                st.divider()


    # --- Session Controls ---
    if st.button("End Session", type="primary"):
        for key in ['session_started', 'attendees', 'waiting_players', 'active_games', 'player_history', 'game_stats']:
            st.session_state[key] = False if isinstance(st.session_state.get(key), bool) else ([] if isinstance(st.session_state.get(key), list) else {})
        st.rerun()
