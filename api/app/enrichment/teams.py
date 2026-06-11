"""NHL opponent-team table and game-identifier extraction (brief 07, Q4)."""
from datetime import datetime
from typing import Optional

# NHL opponent teams mapping (excluding Sharks)
# Maps team names and common variations to 3-letter abbreviations
NHL_OPPONENT_TEAMS = {
    'ducks': 'ANA', 'anaheim': 'ANA',
    'coyotes': 'UTA', 'utah': 'UTA',
    'bruins': 'BOS', 'boston': 'BOS',
    'sabres': 'BUF', 'buffalo': 'BUF',
    'flames': 'CGY', 'calgary': 'CGY',
    'hurricanes': 'CAR', 'carolina': 'CAR',
    'blackhawks': 'CHI', 'chicago': 'CHI',
    'avalanche': 'COL', 'colorado': 'COL',
    'blue jackets': 'CBJ', 'columbus': 'CBJ',
    'stars': 'DAL', 'dallas': 'DAL',
    'red wings': 'DET', 'detroit': 'DET',
    'oilers': 'EDM', 'edmonton': 'EDM',
    'panthers': 'FLA', 'florida': 'FLA',
    'kings': 'LAK', 'los angeles': 'LAK',
    'wild': 'MIN', 'minnesota': 'MIN',
    'canadiens': 'MTL', 'montreal': 'MTL', 'habs': 'MTL',
    'predators': 'NSH', 'nashville': 'NSH',
    'devils': 'NJD', 'new jersey': 'NJD',
    'islanders': 'NYI',
    'rangers': 'NYR',
    'senators': 'OTT', 'ottawa': 'OTT',
    'flyers': 'PHI', 'philadelphia': 'PHI',
    'penguins': 'PIT', 'pittsburgh': 'PIT',
    'kraken': 'SEA', 'seattle': 'SEA',
    'blues': 'STL', 'st louis': 'STL', 'st. louis': 'STL',
    'lightning': 'TBL', 'tampa bay': 'TBL', 'tampa': 'TBL',
    'maple leafs': 'TOR', 'toronto': 'TOR', 'leafs': 'TOR',
    'canucks': 'VAN', 'vancouver': 'VAN',
    'golden knights': 'VGK', 'vegas': 'VGK',
    'capitals': 'WSH', 'washington': 'WSH',
    'jets': 'WPG', 'winnipeg': 'WPG',
}


def extract_game_identifier(text: str, published_at: datetime) -> Optional[str]:
    """
    Extract game identifier (opponent-date) from game-related content.

    Scans text for opponent team mentions and combines with the article's
    published date to create a unique game identifier for clustering.

    Args:
        text: Article title and description combined
        published_at: Article publication timestamp

    Returns:
        Game identifier string like "LAK-2026-01-15" or None if no opponent found
    """
    text_lower = text.lower()

    # Find opponent team in text
    for keyword, team_code in NHL_OPPONENT_TEAMS.items():
        if keyword in text_lower:
            date_str = published_at.strftime('%Y-%m-%d')
            return f"{team_code}-{date_str}"

    return None
