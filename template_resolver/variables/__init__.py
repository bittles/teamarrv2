"""Template variable extractors.

Each module in this package defines variable extractors using the
@register_variable decorator. Variables are organized by category:

- identity: team_name, opponent, league, sport
- datetime: game_date, game_time, days_until
- venue: venue, venue_city, venue_full
- home_away: is_home, vs_at, home_team, away_team
- records: team_record, opponent_record
- streaks: streak, home_streak, last_5_record
- h2h: season_series, rematch_*
- scores: team_score, final_score
- outcome: result, result_text
- standings: playoff_seed, games_back
- statistics: team_ppg, opponent_ppg
- playoffs: is_playoff, season_type
- odds: odds_spread, odds_over_under
- broadcast: broadcast_simple, is_national_broadcast
- rankings: team_rank, is_ranked
- conference: college_conference, pro_division
- soccer: soccer_match_league

Import this module to register all variables with the registry.
"""

from template_resolver.registry import SuffixRules, get_registry

# Import all variable modules to trigger registration (noqa: F401 for side-effect imports)
from template_resolver.variables import (  # noqa: F401
    broadcast,
    conference,
    datetime,
    h2h,
    home_away,
    identity,
    odds,
    outcome,
    playoffs,
    rankings,
    records,
    scores,
    soccer,
    standings,
    statistics,
    streaks,
    venue,
)

__all__ = ["SuffixRules", "get_registry"]
