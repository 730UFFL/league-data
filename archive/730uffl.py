from espn_api.football import League
import pandas as pd
import numpy as np

# ESPN League Configuration
LEAGUE_ID = '634388'  # Found in your ESPN league URL
YEAR = 2025  # Current season year
ESPN_S2 = '<redacted - see .env>'
SWID = '<redacted - see .env>'

def get_weekly_historical_data(league_id, year, espn_s2=None, swid=None):
    """
    Get weekly historical standings data for interactive dashboard
    This calculates how standings looked after each completed week
    """
    try:
        # Initialize league connection
        if espn_s2 and swid:
            league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=league_id, year=year)
        
        # Get all matchup data first
        matchup_data = []
        for week in range(1, league.current_week):
            try:
                scoreboard = league.scoreboard(week)
                for matchup in scoreboard:
                    if matchup.home_team and matchup.away_team:
                        # Home team data
                        matchup_data.append({
                            'week': week,
                            'team_id': matchup.home_team.team_id,
                            'team_name': matchup.home_team.team_name,
                            'score': matchup.home_score,
                            'opponent_score': matchup.away_score,
                            'won': matchup.home_score > matchup.away_score,
                        })
                        
                        # Away team data
                        matchup_data.append({
                            'week': week,
                            'team_id': matchup.away_team.team_id,
                            'team_name': matchup.away_team.team_name,
                            'score': matchup.away_score,
                            'opponent_score': matchup.home_score,
                            'won': matchup.away_score > matchup.home_score,
                        })
            except:
                continue
        
        matchup_df = pd.DataFrame(matchup_data)
        if matchup_df.empty:
            return pd.DataFrame()
        
        # Calculate cumulative standings for each week
        weekly_standings = []
        
        for week in range(1, league.current_week):
            # Get data through this week
            week_data = matchup_df[matchup_df['week'] <= week].copy()
            
            # Calculate cumulative stats by team through this week
            team_stats = week_data.groupby(['team_id', 'team_name']).agg({
                'score': 'sum',  # Points For
                'opponent_score': 'sum',  # Points Against  
                'won': 'sum',  # Wins
                'week': 'count'  # Games played
            }).reset_index()
            
            team_stats.columns = ['team_id', 'team_name', 'PF', 'PA', 'wins', 'games_played']
            team_stats['losses'] = team_stats['games_played'] - team_stats['wins']
            team_stats['week'] = week
            team_stats['win_pct'] = team_stats['wins'] / team_stats['games_played']
            
            # Calculate expected wins for this week (vs league average through this week)
            league_avg_pf = team_stats['PF'].mean() / week  # Average per game
            team_stats['expected_wins'] = team_stats.apply(
                lambda row: sum(1 for w in range(1, week + 1) 
                              if week_data[(week_data['team_id'] == row['team_id']) & 
                                         (week_data['week'] == w)]['score'].iloc[0] > league_avg_pf * w 
                              if len(week_data[(week_data['team_id'] == row['team_id']) & 
                                             (week_data['week'] == w)]) > 0), axis=1
            )
            team_stats['win_luck'] = team_stats['wins'] - team_stats['expected_wins']
            
            weekly_standings.append(team_stats)
        
        return pd.concat(weekly_standings, ignore_index=True)
    
    except Exception as e:
        print(f"Error fetching weekly historical data: {e}")
        return pd.DataFrame()

def get_espn_standings(league_id, year, espn_s2=None, swid=None):
    """
    Fetch current standings from ESPN Fantasy Football API
    """
    try:
        # Initialize league connection
        if espn_s2 and swid:
            league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=league_id, year=year)
        
        # Get current standings data
        standings_data = []
        
        for team in league.teams:
            # Debug: Print available attributes for first team
            if len(standings_data) == 0:
                print("Available team attributes:", [attr for attr in dir(team) if not attr.startswith('_')])
            
            # Try different attribute names for owner information
            owner_name = ""
            if hasattr(team, 'owner'):
                owner_name = team.owner
            elif hasattr(team, 'owners'):
                owner_name = team.owners[0] if team.owners else ""
            elif hasattr(team, 'primaryOwner'):
                owner_name = team.primaryOwner
            
            standings_data.append({
                'RK': getattr(team, 'standing', 0),
                'Team': f"{team.team_name} ({owner_name})" if owner_name else team.team_name, 
                'Record': f"{team.wins}-{team.losses}-{getattr(team, 'ties', 0)}",
                'PF': round(team.points_for, 2),
                'PA': round(team.points_against, 2),
                'Wins': team.wins,
                'Losses': team.losses,
                'Ties': getattr(team, 'ties', 0),
                'Win_Pct': round(team.wins / (team.wins + team.losses + getattr(team, 'ties', 0)) if (team.wins + team.losses + getattr(team, 'ties', 0)) > 0 else 0, 3),
                'Moves': getattr(team, 'acquisitions', 0)
            })
        
        # Convert to DataFrame and sort by standing
        df = pd.DataFrame(standings_data)
        
        # Handle cases where standing might not be available
        if 'RK' in df.columns and df['RK'].notna().any():
            df = df.sort_values('RK').reset_index(drop=True)
        else:
            # Sort by win percentage if standing not available
            df = df.sort_values('Win_Pct', ascending=False).reset_index(drop=True)
            df['RK'] = range(1, len(df) + 1)
        
        return df
    
    except Exception as e:
        print(f"Error fetching data: {e}")
        print("This could be due to:")
        print("1. Incorrect league ID")
        print("2. Private league requiring ESPN_S2 and SWID")
        print("3. Season not yet started (2025)")
        print("4. Network connectivity issues")
        # Return empty DataFrame instead of None
        return pd.DataFrame(columns=['RK', 'Team', 'Record', 'PF', 'PA', 'Wins', 'Losses', 'Ties', 'Win_Pct', 'Moves'])

def get_matchup_data(league_id, year, espn_s2=None, swid=None):
    """
    Get detailed head-to-head matchup data including opponent strength analysis
    """
    try:
        # Initialize league connection
        if espn_s2 and swid:
            league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=league_id, year=year)
        
        matchup_data = []
        
        # Get all matchups for completed weeks
        for week in range(1, league.current_week):
            try:
                scoreboard = league.scoreboard(week)
                for matchup in scoreboard:
                    if matchup.home_team and matchup.away_team:
                        # Home team data
                        matchup_data.append({
                            'week': week,
                            'team_id': matchup.home_team.team_id,
                            'team_name': matchup.home_team.team_name,
                            'score': matchup.home_score,
                            'opponent_id': matchup.away_team.team_id,
                            'opponent_name': matchup.away_team.team_name,
                            'opponent_score': matchup.away_score,
                            'won': matchup.home_score > matchup.away_score,
                            'is_home': True
                        })
                        
                        # Away team data
                        matchup_data.append({
                            'week': week,
                            'team_id': matchup.away_team.team_id,
                            'team_name': matchup.away_team.team_name,
                            'score': matchup.away_score,
                            'opponent_id': matchup.home_team.team_id,
                            'opponent_name': matchup.home_team.team_name,
                            'opponent_score': matchup.home_score,
                            'won': matchup.away_score > matchup.home_score,
                            'is_home': False
                        })
            except:
                continue
        
        return pd.DataFrame(matchup_data)
    
    except Exception as e:
        print(f"Error fetching matchup data: {e}")
        return pd.DataFrame()

def analyze_luck_metrics(matchup_df):
    """
    Calculate various "luck" metrics based on matchup history
    """
    if matchup_df.empty:
        return pd.DataFrame()
    
    # Calculate team season averages
    team_stats = matchup_df.groupby(['team_id', 'team_name']).agg({
        'score': ['mean', 'std'],
        'opponent_score': 'mean',
        'won': ['count', 'sum']
    }).round(2)
    
    # Flatten column names
    team_stats.columns = ['avg_score', 'score_std', 'avg_opp_score', 'games_played', 'wins']
    team_stats = team_stats.reset_index()
    team_stats['win_pct'] = (team_stats['wins'] / team_stats['games_played']).round(3)
    
    luck_metrics = []
    
    for _, team in team_stats.iterrows():
        team_id = team['team_id']
        team_matchups = matchup_df[matchup_df['team_id'] == team_id].copy()
        
        # Calculate opponent strength metrics
        opp_avg_scores = []
        opp_season_records = []
        
        for _, game in team_matchups.iterrows():
            opp_games = matchup_df[matchup_df['team_id'] == game['opponent_id']]
            if not opp_games.empty:
                opp_avg_score = opp_games['score'].mean()
                opp_wins = opp_games['won'].sum()
                opp_games_count = len(opp_games)
                opp_win_pct = opp_wins / opp_games_count if opp_games_count > 0 else 0
                
                opp_avg_scores.append(opp_avg_score)
                opp_season_records.append(opp_win_pct)
        
        # Strength of Schedule metrics
        avg_opp_scoring = np.mean(opp_avg_scores) if opp_avg_scores else 0
        avg_opp_win_pct = np.mean(opp_season_records) if opp_season_records else 0
        
        # Expected wins based on scores (how many games would you win vs league average?)
        league_avg_score = matchup_df['score'].mean()
        expected_wins = sum(1 for score in team_matchups['score'] if score > league_avg_score)
        actual_wins = team['wins']
        win_luck = actual_wins - expected_wins
        
        # Points luck - how much did opponents under/over perform their averages against you?
        opponent_diff = []
        for _, game in team_matchups.iterrows():
            opp_games = matchup_df[matchup_df['team_id'] == game['opponent_id']]
            if not opp_games.empty:
                opp_avg = opp_games['score'].mean()
                opponent_diff.append(game['opponent_score'] - opp_avg)
        
        avg_opp_performance_diff = np.mean(opponent_diff) if opponent_diff else 0
        
        luck_metrics.append({
            'team_id': team_id,
            'team_name': team['team_name'],
            'actual_wins': actual_wins,
            'expected_wins': expected_wins,
            'win_luck': win_luck,
            'avg_opp_scoring': round(avg_opp_scoring, 2),
            'avg_opp_win_pct': round(avg_opp_win_pct, 3),
            'strength_of_schedule': round(avg_opp_win_pct, 3),  # Higher = harder schedule
            'opponent_performance_vs_avg': round(avg_opp_performance_diff, 2),  # Negative = opponents underperformed
            'games_played': team['games_played']
        })
    
    return pd.DataFrame(luck_metrics)

def get_remaining_schedule(league_id, year, espn_s2=None, swid=None):
    """
    Get remaining schedule and calculate future strength of schedule
    """
    try:
        # Initialize league connection
        if espn_s2 and swid:
            league = League(league_id=league_id, year=year, espn_s2=espn_s2, swid=swid)
        else:
            league = League(league_id=league_id, year=year)
        
        future_matchups = []
        current_week = league.current_week
        
        # Look at remaining weeks (assuming 17 week season)
        for week in range(current_week, 18):
            try:
                scoreboard = league.scoreboard(week)
                for matchup in scoreboard:
                    if matchup.home_team and matchup.away_team:
                        future_matchups.append({
                            'week': week,
                            'team_id': matchup.home_team.team_id,
                            'team_name': matchup.home_team.team_name,
                            'opponent_id': matchup.away_team.team_id,
                            'opponent_name': matchup.away_team.team_name,
                            'is_home': True
                        })
                        
                        future_matchups.append({
                            'week': week,
                            'team_id': matchup.away_team.team_id,
                            'team_name': matchup.away_team.team_name,
                            'opponent_id': matchup.home_team.team_id,
                            'opponent_name': matchup.home_team.team_name,
                            'is_home': False
                        })
            except:
                continue
        
        return pd.DataFrame(future_matchups)
    
    except Exception as e:
        print(f"Error fetching future schedule: {e}")
        return pd.DataFrame()

# Usage example with better error handling:
standings_df = get_espn_standings(LEAGUE_ID, YEAR, ESPN_S2, SWID)

if not standings_df.empty:
    standings_df.to_csv('espn_standings.csv', index=False)
    print("Successfully saved standings to espn_standings.csv")
    print(standings_df)
    
    # Get matchup data and analyze luck
    print("\n" + "="*50)
    print("ANALYZING HEAD-TO-HEAD MATCHUPS AND LUCK METRICS")
    print("="*50)
    
    matchup_df = get_matchup_data(LEAGUE_ID, YEAR, ESPN_S2, SWID)
    if not matchup_df.empty:
        matchup_df.to_csv('matchup_history.csv', index=False)
        print(f"Successfully saved {len(matchup_df)} matchup records to matchup_history.csv")
        
        # Analyze luck metrics
        luck_analysis = analyze_luck_metrics(matchup_df)
        if not luck_analysis.empty:
            luck_analysis.to_csv('luck_analysis.csv', index=False)
            print("Successfully saved luck analysis to luck_analysis.csv")
            
            # Show the most/least lucky teams
            print("\nLUCK ANALYSIS (Win Luck = Actual Wins - Expected Wins):")
            print("="*60)
            luck_sorted = luck_analysis.sort_values('win_luck', ascending=False)
            for _, team in luck_sorted.iterrows():
                luck_indicator = "🍀" if team['win_luck'] > 0 else "💩" if team['win_luck'] < 0 else "😐"
                print(f"{luck_indicator} {team['team_name'][:20]:<20} | Win Luck: {team['win_luck']:+.0f} | SOS: {team['strength_of_schedule']:.3f}")
        
        # Get future schedule
        future_df = get_remaining_schedule(LEAGUE_ID, YEAR, ESPN_S2, SWID)
        if not future_df.empty:
            future_df.to_csv('future_schedule.csv', index=False)
            print(f"\nSuccessfully saved future schedule to future_schedule.csv")
    
    # NEW: Get weekly historical data for dashboard
    print("\n" + "="*50)
    print("COLLECTING WEEKLY HISTORICAL DATA FOR DASHBOARD")
    print("="*50)
    
    weekly_data = get_weekly_historical_data(LEAGUE_ID, YEAR, ESPN_S2, SWID)
    if not weekly_data.empty:
        weekly_data.to_csv('weekly_historical_data.csv', index=False)
        print(f"Successfully saved {len(weekly_data)} weekly records to weekly_historical_data.csv")
        print("This data shows how standings evolved week by week!")
        
        # Show sample of weekly progression
        print("\nSample Weekly Progression (Week 1 vs Latest):")
        print("-" * 50)
        week1_data = weekly_data[weekly_data['week'] == 1].sort_values('win_pct', ascending=False)
        latest_week = weekly_data['week'].max()
        latest_data = weekly_data[weekly_data['week'] == latest_week].sort_values('win_pct', ascending=False)
        
        print("WEEK 1 STANDINGS:")
        for _, team in week1_data.head(3).iterrows():
            print(f"  {team['team_name'][:15]:<15} | {team['wins']}-{team['losses']} | PF: {team['PF']:.1f}")
            
        print(f"\nWEEK {latest_week} STANDINGS:")
        for _, team in latest_data.head(3).iterrows():
            print(f"  {team['team_name'][:15]:<15} | {team['wins']}-{team['losses']} | PF: {team['PF']:.1f}")
    
else:
    print("No data retrieved - check your league configuration")
    print("No data retrieved - check your league configuration")
