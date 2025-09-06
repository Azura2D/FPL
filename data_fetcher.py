# data_fetcher.py

"""
This module is responsible for all interactions with the FPL Draft API.
It fetches, processes, and enriches the raw data into structured pandas DataFrames
suitable for display in the application. It includes caching and robust error handling.
"""
import requests
import pandas as pd
import time
from collections import defaultdict

# --- Constants ---
BASE_URL = "https://draft.premierleague.com/api"
BOOTSTRAP_URL = f"{BASE_URL}/bootstrap-static"
LEAGUE_URL_TEMPLATE = f"{BASE_URL}/league/{{league_id}}/details"
ELEMENT_STATUS_URL_TEMPLATE = f"{BASE_URL}/league/{{league_id}}/element-status"

# --- In-Memory Cache ---
DATA_CACHE = {}
CACHE_DURATION_SECONDS = 600

def _get_json_from_url(url: str):
    """Safely gets JSON from a URL."""
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except (requests.exceptions.RequestException, requests.exceptions.JSONDecodeError) as e:
        print(f"[data_fetcher] ERROR: Failed to fetch or decode {url}: {e}")
        return None

def _calculate_rank(diff):
    """Calculates a 1-10 rank based on performance vs. expectation."""
    if diff >= 8: return 10
    if diff >= 4: return 8
    if diff >= 2: return 7
    if diff >= 0: return 6
    if diff > -2: return 5
    return 1

def _calculate_team_form_difficulty(bootstrap_data):
    """Calculates a dynamic difficulty score based on the last 5 results of opponents."""
    print("[data_fetcher] Calculating dynamic team form difficulty...")
    fixtures = bootstrap_data.get('fixtures', [])
    if not fixtures: return None

    team_results = defaultdict(list)
    finished_fixtures = [f for f in fixtures if isinstance(f, dict) and f.get('finished')]
    for fix in sorted(finished_fixtures, key=lambda x: x.get('event', 0)):
        team_h_score, team_a_score = fix.get('team_h_score'), fix.get('team_a_score')
        if team_h_score is not None and team_a_score is not None:
            if team_h_score > team_a_score: team_results[fix['team_h']].append('W'); team_results[fix['team_a']].append('L')
            elif team_a_score > team_h_score: team_results[fix['team_a']].append('W'); team_results[fix['team_h']].append('L')
            else: team_results[fix['team_h']].append('D'); team_results[fix['team_a']].append('D')

    form_scores = {team_id: sum([3 if r == 'W' else 1 if r == 'D' else 0 for r in results[-5:]]) for team_id, results in team_results.items()}
    if not form_scores: return None
    
    min_score, max_score = min(form_scores.values()), max(form_scores.values())
    
    team_form_difficulty = {}
    for team_id, score in form_scores.items():
        if max_score == min_score: normalized_score = 3.0
        else: normalized_score = 1 + 4 * (score - min_score) / (max_score - min_score)
        team_form_difficulty[team_id] = normalized_score
        
    return pd.DataFrame(list(team_form_difficulty.items()), columns=['id', 'Form Difficulty'])

def _process_fixtures(bootstrap_data, teams_df):
    """Processes fixtures to calculate a blended average difficulty."""
    print("[data_fetcher] Processing fixture data...")
    fixtures = bootstrap_data.get('fixtures')
    if not fixtures: return None

    try:
        current_gw = next(event['id'] for event in bootstrap_data.get('events', []) if isinstance(event, dict) and event.get('is_current'))
    except StopIteration: current_gw = 1

    form_difficulty_df = _calculate_team_form_difficulty(bootstrap_data)
    form_map = form_difficulty_df.set_index('id')['Form Difficulty'].to_dict() if form_difficulty_df is not None else {}
    
    team_fixtures = defaultdict(list)
    for fix in fixtures:
        if isinstance(fix, dict) and fix.get('event') and fix['event'] >= current_gw:
            team_fixtures[fix['team_h']].append({'opp_id': fix['team_a'], 'fpl_diff': fix['team_h_difficulty']})
            team_fixtures[fix['team_a']].append({'opp_id': fix['team_h'], 'fpl_diff': fix['team_a_difficulty']})

    team_avg_difficulty = {}
    for team_id, future_games in team_fixtures.items():
        difficulties = []
        for game in future_games[:3]:
            fpl_diff = game['fpl_diff']
            form_diff = form_map.get(game['opp_id'], 3.0) # Use the map for a safe lookup
            combined_diff = (fpl_diff * 0.6) + (form_diff * 0.4)
            difficulties.append(combined_diff)
        if difficulties: team_avg_difficulty[team_id] = sum(difficulties) / len(difficulties)

    difficulty_df = pd.DataFrame(list(team_avg_difficulty.items()), columns=['id', 'Avg Difficulty'])
    teams_with_difficulty = teams_df.merge(difficulty_df, on='id', how='left')
    teams_with_difficulty['Avg Difficulty'] = teams_with_difficulty['Avg Difficulty'].fillna(3.0)
    
    return teams_with_difficulty[['id', 'Avg Difficulty']]

def fetch_fpl_data(league_id: int, force_refresh: bool = False):
    current_time = time.time()
    if not force_refresh and league_id in DATA_CACHE and (current_time - DATA_CACHE[league_id]['timestamp'] < CACHE_DURATION_SECONDS):
        return DATA_CACHE[league_id]['data']

    bootstrap = _get_json_from_url(BOOTSTRAP_URL)
    if not bootstrap or 'elements' not in bootstrap: return None, None, None

    players_df, teams_df, pos_df = pd.DataFrame(bootstrap['elements']), pd.DataFrame(bootstrap['teams']), pd.DataFrame(bootstrap['element_types'])
    league_data = _get_json_from_url(LEAGUE_URL_TEMPLATE.format(league_id=league_id))
    if not league_data: return None, None, None
    
    difficulty_df = _process_fixtures(bootstrap, teams_df)
    if difficulty_df is not None: teams_df = teams_df.merge(difficulty_df, on='id', how='left')
    if 'Avg Difficulty' not in teams_df.columns: teams_df['Avg Difficulty'] = 3.0

    players_df = players_df.merge(teams_df[['id', 'name', 'Avg Difficulty']], left_on='team', right_on='id', how='left', suffixes=('', '_team')).rename(columns={'name': 'team_name'}).drop(columns=['id_team'])
    players_df = players_df.merge(pos_df[['id', 'singular_name']], left_on='element_type', right_on='id', how='left', suffixes=('', '_pos')).rename(columns={'singular_name': 'position'}).drop(columns=['id_pos'])
    
    players_df.rename(columns={'ep_next': 'Expected Points Next', 'ep_this': 'Expected Points Prev GW', 'event_points': 'Points Prev GW'}, inplace=True)
    
    for col in ['points_per_game', 'Expected Points Next', 'Expected Points Prev GW', 'Points Prev GW', 'form', 'Avg Difficulty']:
        if col in players_df.columns: players_df[col] = pd.to_numeric(players_df[col], errors='coerce').fillna(0)
    
    players_df['EP Diff'] = players_df['Points Prev GW'] - players_df['Expected Points Prev GW']
    players_df['Rank'] = players_df['EP Diff'].apply(_calculate_rank)

    entry_id_to_name = {e['entry_id']: e['entry_name'] for e in league_data.get('league_entries', []) if isinstance(e, dict)}
    status_url = ELEMENT_STATUS_URL_TEMPLATE.format(league_id=league_id)
    status_data = _get_json_from_url(status_url)
    
    player_to_team = {s['element']: entry_id_to_name.get(s['owner']) for s in (status_data or {}).get('element_status', []) if isinstance(s, dict) and s.get('owner')}
    players_df['owner'] = players_df['id'].map(player_to_team)
    
    teams_tables = {t: players_df[players_df['owner'] == t].copy().sort_values('total_points', ascending=False) for t in set(player_to_team.values()) if t}
    undrafted = players_df[players_df['owner'].isna()].copy().sort_values('total_points', ascending=False)

    result = (players_df, teams_tables, undrafted)
    DATA_CACHE[league_id] = {'timestamp': current_time, 'data': result}
    
    return result