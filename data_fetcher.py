# data_fetcher.py

"""
This module is responsible for all interactions with the FPL Draft API.
It fetches, processes, and enriches the raw data into structured pandas DataFrames
suitable for display in the application. It includes caching and robust error handling.
"""
import requests
import pandas as pd
import time

# --- Constants ---
BASE_URL = "https://draft.premierleague.com/api"
BOOTSTRAP_URL = f"{BASE_URL}/bootstrap-static"
LEAGUE_URL_TEMPLATE = f"{BASE_URL}/league/{{league_id}}/details"
DRAFT_CHOICES_URL_TEMPLATE = f"{BASE_URL}/draft/{{league_id}}/choices"
LIVE_EVENT_URL_TEMPLATE = f"{BASE_URL}/event/{{gameweek}}/live"

# --- In-Memory Cache ---
# A simple dictionary to cache results from the API to avoid redundant calls.
DATA_CACHE = {}
CACHE_DURATION_SECONDS = 600  # 10 minutes

def _get_json_from_url(url: str):
    """
    Safely gets JSON from a URL, handling network errors, bad status codes,
    and non-JSON responses. Returns None on failure.
    """
    try:
        print(f"[data_fetcher] Fetching URL: {url}")
        response = requests.get(url)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4xx or 5xx)
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[data_fetcher] ERROR: Network error fetching {url}: {e}")
        return None
    except requests.exceptions.JSONDecodeError:
        print(f"[data_fetcher] ERROR: Failed to decode JSON from {url}. Response text: {response.text}")
        return None

def fetch_fpl_data(league_id: int, force_refresh: bool = False):
    """
    Orchestrates the entire data fetching and processing pipeline.
    1. Checks cache.
    2. Fetches data from multiple API endpoints.
    3. Cleans and merges the data into a master player DataFrame.
    4. Segregates players into drafted and undrafted tables.
    """
    # --- Cache Check ---
    current_time = time.time()
    print("[data_fetcher] Starting data fetch process...")
    if not force_refresh and league_id in DATA_CACHE and (current_time - DATA_CACHE[league_id]['timestamp'] < CACHE_DURATION_SECONDS):
        print(f"[data_fetcher] Cache hit for league {league_id}. Returning cached data.")
        return DATA_CACHE[league_id]['data']
    print(f"[data_fetcher] Cache miss or refresh forced for league {league_id}.")

    # ====== 1. Fetch Core Data ======
    print("[data_fetcher] Fetching core bootstrap and league data...")
    bootstrap = _get_json_from_url(BOOTSTRAP_URL)
    if not bootstrap or 'elements' not in bootstrap:
        print("Critical error: Failed to fetch or validate bootstrap data.")
        return None, None, None

    # --- Validate Bootstrap Data Structure ---
    # Ensures that the core data structures from the bootstrap endpoint are lists before creating DataFrames.
    # This prevents TypeErrors if the API returns unexpected data types.
    for key in ['elements', 'teams', 'element_types']:
        if not isinstance(bootstrap.get(key), list):
            print(f"Critical error: Bootstrap data for '{key}' is not a list as expected.")
            return None, None, None

    players_df = pd.DataFrame(bootstrap['elements'])
    teams_df = pd.DataFrame(bootstrap['teams'])
    positions_df = pd.DataFrame(bootstrap['element_types'])
    print("[data_fetcher] Core DataFrames created.")

    league_url = LEAGUE_URL_TEMPLATE.format(league_id=league_id)
    league_data = _get_json_from_url(league_url)
    if not league_data or 'league_entries' not in league_data:
        print(f"Critical error: Failed to fetch or validate league data for league {league_id}.")
        return None, None, None
    
    # ====== 2. Process and Enrich Data ======
    print("[data_fetcher] Enriching player data with team, position, and owner info...")
    # Enrich player data with team names and positions.
    players_df = players_df.merge(
        teams_df[['id', 'name']], left_on='team', right_on='id', how='left', suffixes=('', '_team')
    ).rename(columns={'name': 'team_name'}).drop(columns=['id_team'])

    players_df = players_df.merge(
        positions_df[['id', 'singular_name']], left_on='element_type', right_on='id', how='left', suffixes=('', '_pos')
    ).rename(columns={'singular_name': 'position'}).drop(columns=['id_pos'])

    # Create a mapping of league entry IDs to team names.
    # A for-loop is used for robustness, preventing TypeErrors if the API returns non-dictionary items.
    entry_id_to_name = {}
    for entry in league_data.get('league_entries', []):
        if isinstance(entry, dict) and 'entry_id' in entry and 'entry_name' in entry:
            entry_id_to_name[entry['entry_id']] = entry['entry_name']

    # Map each drafted player to their owner's team name.
    draft_picks_url = DRAFT_CHOICES_URL_TEMPLATE.format(league_id=league_id)
    draft_picks_data = _get_json_from_url(draft_picks_url)

    player_to_team = {}
    if draft_picks_data and isinstance(draft_picks_data.get('choices'), list):
        for pick in draft_picks_data['choices']:
            if isinstance(pick, dict):
                player_id = pick.get('element')
                entry_id = pick.get('entry')
                if player_id and entry_id and entry_id in entry_id_to_name:
                    player_to_team[player_id] = entry_id_to_name[entry_id]
    
    players_df['owner'] = players_df['id'].map(player_to_team)
    print("[data_fetcher] Player data enrichment complete.")

    # ====== 3. Fetch Recent Gameweek Stats for Cumulative Totals ======
    print("[data_fetcher] Fetching recent gameweek stats...")
    # This is done robustly to handle cases where 'events' contains non-dictionary items.
    current_gw_data = next((event for event in bootstrap.get('events', [])
                            if isinstance(event, dict) and event.get('is_current')),
                           None)
    current_gw = current_gw_data['id'] if current_gw_data else 1
    gameweeks_to_fetch = list(range(max(1, current_gw - 3), current_gw + 1))

    gameweek_stats_list = []
    # Fetch live data for the last few gameweeks to calculate cumulative stats.
    for gameweek in gameweeks_to_fetch:
        gameweek_url = LIVE_EVENT_URL_TEMPLATE.format(gameweek=gameweek)
        gameweek_live_data = _get_json_from_url(gameweek_url)
        
        if gameweek_live_data and isinstance(gameweek_live_data.get('elements'), dict):
            for player_id, player_data in gameweek_live_data['elements'].items():
                stats = player_data.get('stats', {})
                stats['id'] = int(player_id)
                stats['gameweek'] = gameweek
                gameweek_stats_list.append(stats)

    if not gameweek_stats_list:
        gameweek_stats_df = pd.DataFrame(columns=['id', 'gameweek'])
    else:
        gameweek_stats_df = pd.DataFrame(gameweek_stats_list)
    print(f"[data_fetcher] Found {len(gameweek_stats_list)} gameweek stat entries.")

    merged_df = players_df.merge(gameweek_stats_df, on='id', how='left', suffixes=('', '_gw_stats'))
    print("[data_fetcher] Calculating cumulative points...")
    
    # --- Calculate Cumulative Points (Robustly) ---
    # An explicit check for the column's existence is used for robustness.
    if 'total_points_gw_stats' in merged_df.columns:
        merged_df['total_points_gw_stats'] = pd.to_numeric(merged_df['total_points_gw_stats'], errors='coerce')
        cumulative_points_df = merged_df.groupby('id')['total_points_gw_stats'].sum().reset_index()
        cumulative_points_df.rename(columns={'total_points_gw_stats': 'cumulative_total_points'}, inplace=True)
    else:
        # If no gameweek data was found, create a cumulative points column initialized to zero.
        cumulative_points_df = players_df[['id']].copy()
        cumulative_points_df['cumulative_total_points'] = 0

    players_df = players_df.merge(cumulative_points_df, on='id', how='left')
    players_df['cumulative_total_points'] = players_df['cumulative_total_points'].fillna(0).astype(int)
    print("[data_fetcher] Cumulative points calculation complete.")
    
    # ====== 4. Create Final Output Tables ======
    print("[data_fetcher] Segregating players into drafted and undrafted tables...")
    teams_tables = {
        team: players_df[players_df['owner'] == team].copy().sort_values('cumulative_total_points', ascending=False).reset_index(drop=True)
        for team in set(players_df['owner'].dropna().unique())
    }
    undrafted_table = players_df[players_df['owner'].isna()].copy().sort_values('cumulative_total_points', ascending=False).reset_index(drop=True)

    # ====== 5. Cache the Result ======
    print("[data_fetcher] Caching new data...")
    result = (players_df, teams_tables, undrafted_table)
    DATA_CACHE[league_id] = {'timestamp': current_time, 'data': result}
    
    print("[data_fetcher] Data fetch process finished successfully.")
    return result
