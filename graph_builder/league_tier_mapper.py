"""
League tier and mass mapping utility for classifying player moves.

Provides singleton access to league competition data for determining
move direction (up/down/lateral) based on tier and market value mass.
"""

import json
from pathlib import Path
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class LeagueInfo:
    """Information about a league/competition."""
    tier: int
    total_market_value: float  # in millions EUR
    competition_name: str
    competition_code: str
    country: str
    confederation: str


class LeagueTierMapper:
    """
    Singleton for mapping clubs to league tier and mass information.
    
    Uses hybrid classification:
    - Primary: tier difference (lower tier number = higher quality)
    - Tiebreaker: mass ratio (≥1.5 threshold)
    """
    
    _instance: Optional['LeagueTierMapper'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._club_to_league: Dict[str, LeagueInfo] = {}
            self._club_tm_id_to_league: Dict[str, LeagueInfo] = {}
            self._load_league_data()
            LeagueTierMapper._initialized = True
    
    def _load_league_data(self):
        """Load league clubs enriched data from most recent file."""
        data_dir = Path("data/extracted")
        
        # Find most recent league_clubs_enriched file
        league_files = list(data_dir.glob("league_clubs_enriched_*.jsonl"))
        if not league_files:
            print("Warning: No league_clubs_enriched files found")
            return
        
        latest_file = max(league_files, key=lambda p: p.stat().st_mtime)
        print(f"Loading league data from {latest_file.name}")
        
        count = 0
        with open(latest_file, 'r') as f:
            for line in f:
                record = json.loads(line)
                
                # Extract league-level info
                tier = record.get('tier', 99)
                competition = record.get('competition', {})
                comp_name = competition.get('name', 'Unknown')
                comp_code = competition.get('code', 'UNK')
                country = record.get('country', 'Unknown')
                confederation = record.get('confederation', 'unknown')
                
                # Get summary total_market_value if available
                summary = record.get('summary', {})
                league_total_mv = summary.get('total_market_value', 0.0)
                
                # Process each club in this league
                clubs = record.get('clubs', [])
                for club in clubs:
                    club_name = club.get('name')
                    club_tm_id = club.get('tm_id')
                    club_total_mv = club.get('total_market_value', 0.0)
                    
                    if not club_name:
                        continue
                    
                    league_info = LeagueInfo(
                        tier=tier,
                        total_market_value=league_total_mv,
                        competition_name=comp_name,
                        competition_code=comp_code,
                        country=country,
                        confederation=confederation
                    )
                    
                    # Store by both name and tm_id
                    self._club_to_league[club_name] = league_info
                    if club_tm_id:
                        self._club_tm_id_to_league[club_tm_id] = league_info
                    count += 1
        
        print(f"Loaded {count} club-to-league mappings")
    
    def get_league_info(self, club_identifier: Optional[str], date: Optional[datetime] = None) -> Optional[LeagueInfo]:
        """
        Get league information for a club.
        
        Args:
            club_identifier: Club name or Transfermarkt ID
            date: Date for temporal lookup (currently unused, for future expansion)
        
        Returns:
            LeagueInfo if found, None otherwise
        """
        if not club_identifier:
            return None
        
        # Try as tm_id first
        if club_identifier in self._club_tm_id_to_league:
            return self._club_tm_id_to_league[club_identifier]
        
        # Try as club name
        if club_identifier in self._club_to_league:
            return self._club_to_league[club_identifier]
        
        return None
    
    def classify_move(
        self,
        from_club: Optional[str],
        to_club: Optional[str],
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None
    ) -> str:
        """
        Classify a player move based on league tier and mass.
        
        Hybrid classification:
        1. If tier differs, use tier (lower number = better league)
        2. If same tier, use mass ratio with 1.5 threshold
        
        Returns:
            One of: "stay", "domestic_up", "domestic_down", "domestic_lateral",
                   "international_up", "international_down", "international_lateral",
                   "unknown_tier"
        """
        # Handle stay (no move)
        if not from_club or not to_club or from_club == to_club:
            return "stay"
        
        from_league = self.get_league_info(from_club, from_date)
        to_league = self.get_league_info(to_club, to_date)
        
        # Handle unknown leagues
        if not from_league or not to_league:
            return "unknown_tier"
        
        # Determine if domestic or international
        is_domestic = from_league.country == to_league.country
        prefix = "domestic" if is_domestic else "international"
        
        # Primary classification: tier difference
        tier_diff = from_league.tier - to_league.tier
        
        if tier_diff > 0:
            # Moving to lower tier number = moving up
            return f"{prefix}_up"
        elif tier_diff < 0:
            # Moving to higher tier number = moving down
            return f"{prefix}_down"
        
        # Same tier: use mass ratio as tiebreaker
        from_mass = from_league.total_market_value
        to_mass = to_league.total_market_value
        
        if from_mass > 0 and to_mass > 0:
            mass_ratio = to_mass / from_mass
            
            if mass_ratio >= 1.5:
                return f"{prefix}_up"
            elif mass_ratio <= (1.0 / 1.5):
                return f"{prefix}_down"
        
        # Same tier, similar mass
        return f"{prefix}_lateral"
    
    def get_stats(self) -> Dict[str, int]:
        """Get mapping statistics."""
        return {
            "total_clubs_by_name": len(self._club_to_league),
            "total_clubs_by_id": len(self._club_tm_id_to_league),
        }


# Singleton instance accessor
def get_league_tier_mapper() -> LeagueTierMapper:
    """Get the singleton LeagueTierMapper instance."""
    return LeagueTierMapper()
