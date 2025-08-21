import streamlit as st
import time
import random
import datetime

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
        # Players available for the very next game
        st.session_state.waiting_players = []
    if 'finished_players' not in st.session_state:
        # Players who have finished a game and are waiting for the round to end
        st.session_state.finished_players = []
    if 'active_games' not in st.session_state:
        st.session_state.active_games = []
    if 'last_match_result' not in st.session_state:
        # Tracks player's last result {'player_id': 'win'/'loss'}
        st.session_state.last_match_result = {}

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
            st.session_state.session_started = True
            st.rerun()

else: # Session is active
    # --- Matchmaking Logic ---
    def create_new_round():
        # Combine waiting and finished players for the new round
        available_players = st.session_state.waiting_players + st.session_state.finished_players
        st.session_state.finished_players = []
        
        # Separate winners and losers
        winners = [p for p in available_players if st.session_state.last_match_result.get(p['id']) == 'win']
        losers = [p for p in available_players if st.session_state.last_match_result.get(p['id']) == 'loss']
        neutral = [p for p in available_players if p['id'] not in st.session_state.last_match_result]
        
        # Shuffle each pool to add randomness
        random.shuffle(winners)
        random.shuffle(losers)
        random.shuffle(neutral)

        # Prioritize matching winners with winners, losers with losers
        potential_players = winners + losers + neutral
        
        while len(potential_players) >= 4 and len(st.session_state.active_games) < MAX_COURTS:
            game_players = potential_players[:4]
            potential_players = potential_players[4:]

            game_players.sort(key=lambda p: p['skill'], reverse=True)
            team1 = [game_players[0], game_players[3]]
            team2 = [game_players[1], game_players[2]]

            used_court_ids = {g['court_id'] for g in st.session_state.active_games}
            next_court_id = next(i for i in range(1, MAX_COURTS + 2) if i not in used_court_ids)

            st.session_state.active_games.append({
                'court_id': next_court_id,
                'team1': team1,
                'team2': team2,
            })
        
        # Remaining players go back to the waiting pool
        st.session_state.waiting_players = potential_players


    # --- Main Display Logic ---
    st.header("Session Status")
    
    # If no games are active, and there are players waiting, start a new round
    if not st.session_state.active_games and (st.session_state.waiting_players or st.session_state.finished_players):
        create_new_round()
        st.rerun()

    # --- Player Pools Display ---
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Waiting for Next Game")
        if not st.session_state.waiting_players:
            st.info("No players are waiting.")
        else:
            player_tags = [f"{p['name']} ({SKILL_MAP[p['skill']]})" for p in st.session_state.waiting_players]
            st.write(" | ".join(player_tags))
    
    with col2:
        st.subheader("Finished, Waiting for Round to End")
        if not st.session_state.finished_players:
            st.info("No players have finished yet.")
        else:
            player_tags = [f"{p['name']} ({SKILL_MAP[p['skill']]})" for p in st.session_state.finished_players]
            st.write(" | ".join(player_tags))

    # --- Active Courts Display ---
    st.header("Active Courts")
    if not st.session_state.active_games:
        st.success("All courts are free! A new round will start shortly.")
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
                        # Determine winners and losers
                        winners, losers = (game['team1'], game['team2']) if score1 > score2 else (game['team2'], game['team1'])
                        
                        # Update last match result for each player
                        for p in winners:
                            st.session_state.last_match_result[p['id']] = 'win'
                        for p in losers:
                            st.session_state.last_match_result[p['id']] = 'loss'
                            
                        # Move players to the finished pool
                        st.session_state.finished_players.extend(game['team1'])
                        st.session_state.finished_players.extend(game['team2'])
                        
                        # Remove game from active list
                        st.session_state.active_games = [g for g in st.session_state.active_games if g['court_id'] != game['court_id']]
                        st.rerun()

    # --- Session Controls ---
    st.divider()
    if st.button("End Session", type="primary"):
        for key in ['session_started', 'attendees', 'waiting_players', 'finished_players', 'active_games', 'last_match_result']:
            st.session_state[key] = False if isinstance(st.session_state.get(key), bool) else ([] if isinstance(st.session_state.get(key), list) else {})
        st.rerun()
