"""
Player market value transition analyzer.

Processes individual players to compute market value transitions with
temporal features (log returns, rate per day) and contextual labels.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import math

from graph_builder.league_tier_mapper import get_league_tier_mapper


@dataclass
class TransitionRow:
    """A single market value transition record."""
    player_id: str
    age_at_d0: float
    position: str
    position_group: str  # GK, DEF, MID, FWD
    age_band: str  # Coarse bands: U21, 21-24, 25-28, 29+
    
    # Two-layer move classification
    moved: bool  # True if club changed (doesn't require league mapping)
    move_dir: str  # up/down/lateral/unknown (only meaningful if moved=True)
    mapping_ok: bool  # True if both clubs mapped to leagues
    
    d0: str  # ISO format date
    d1: str  # ISO format date
    dt_days: int
    log_return: float
    rate_per_day: float
    rate_per_30day: float  # Normalized to 30-day horizon
    v0: float  # Market value at d0 (millions EUR)
    v1: float  # Market value at d1 (millions EUR)
    
    # Club/league context (nullable)
    from_club: Optional[str]
    to_club: Optional[str]
    from_tier: Optional[int]
    to_tier: Optional[int]
    from_mass: Optional[float]
    to_mass: Optional[float]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


class PlayerTransitionAnalyzer:
    """
    Analyzer for computing player market value transitions.
    
    Processes individual players to extract transition sequences from
    market value history, detects transfers via club changes, and
    classifies moves using league tier/mass data.
    """
    
    def __init__(self):
        self.league_mapper = get_league_tier_mapper()
    
    def _get_position_group(self, position: str) -> str:
        """Map granular position to 4 major groups."""
        position = position.upper()
        
        if position == 'GK':
            return 'GK'
        elif position in ['CB', 'LB', 'RB']:
            return 'DEF'
        elif position in ['DM', 'CM', 'AM']:
            return 'MID'
        elif position in ['LW', 'RW', 'CF', 'ST']:
            return 'FWD'
        else:
            return 'UNK'
    
    def _get_age_band(self, age: float) -> str:
        """Map age to coarse bands: U21, 21-24, 25-28, 29+."""
        if age < 21:
            return 'U21'
        elif age < 25:
            return '21-24'
        elif age < 29:
            return '25-28'
        else:
            return '29+'
    
    def analyze_player(self, player_tm_id: str, player_data: Optional[Dict] = None) -> List[TransitionRow]:
        """
        Analyze a single player's market value transitions.
        
        Args:
            player_tm_id: Transfermarkt player ID
            player_data: Optional pre-loaded player data (if None, loads from file)
        
        Returns:
            List of TransitionRow objects
        """
        if player_data is None:
            player_data = self._load_player_data(player_tm_id)
        
        if not player_data:
            return []
        
        # Extract player biographical info
        player_info = player_data.get('data', {}).get('player', {})
        position = player_info.get('position', 'UNK')
        dob_str = player_info.get('date_of_birth')
        
        if not dob_str:
            return []
        
        dob = self._parse_date(dob_str)
        if not dob:
            return []
        
        # Get market value history
        mv_history = player_data.get('data', {}).get('market_values', [])
        
        if len(mv_history) < 2:
            return []
        
        # Sort by date
        mv_history_sorted = sorted(mv_history, key=lambda x: x.get('date', ''))
        
        # Generate transitions
        transitions = []
        for i in range(len(mv_history_sorted) - 1):
            mv0 = mv_history_sorted[i]
            mv1 = mv_history_sorted[i + 1]
            
            transition = self._create_transition(
                player_tm_id=player_tm_id,
                position=position,
                dob=dob,
                mv0=mv0,
                mv1=mv1
            )
            
            if transition:
                transitions.append(transition)
        
        return transitions
    
    def _create_transition(
        self,
        player_tm_id: str,
        position: str,
        dob: datetime,
        mv0: Dict,
        mv1: Dict
    ) -> Optional[TransitionRow]:
        """Create a single transition row from consecutive market values."""
        
        # Parse dates
        d0_str = mv0.get('date')
        d1_str = mv1.get('date')
        
        if not d0_str or not d1_str:
            return None
        
        d0 = self._parse_date(d0_str)
        d1 = self._parse_date(d1_str)
        
        if not d0 or not d1:
            return None
        
        # Calculate time delta
        dt_days = (d1 - d0).days
        
        if dt_days <= 0:
            return None
        
        # Get market values (in EUR, convert to millions)
        v0_raw = mv0.get('value', 0)
        v1_raw = mv1.get('value', 0)
        
        if v0_raw <= 0 or v1_raw <= 0:
            return None
        
        v0 = v0_raw / 1_000_000
        v1 = v1_raw / 1_000_000
        
        # Calculate log return and rate
        log_return = math.log(v1 / v0)
        rate_per_day = log_return / dt_days
        
        # Calculate age at d0
        age_at_d0 = (d0 - dob).days / 365.25
        
        # Get club information
        from_club = mv0.get('club')
        to_club = mv1.get('club')
        
        # Two-layer move classification
        # Layer 1: Did the player move? (no mapping required)
        moved = bool(from_club and to_club and from_club != to_club)
        
        # Layer 2: Get league context (optional, may fail)
        from_league = self.league_mapper.get_league_info(from_club, d0) if from_club else None
        to_league = self.league_mapper.get_league_info(to_club, d1) if to_club else None
        
        mapping_ok = bool(from_league and to_league)
        
        from_tier = from_league.tier if from_league else None
        to_tier = to_league.tier if to_league else None
        from_mass = from_league.total_market_value if from_league else None
        to_mass = to_league.total_market_value if to_league else None
        
        # Compute move direction (only if mapping succeeded)
        if not moved:
            move_dir = 'stay'
        elif not mapping_ok:
            move_dir = 'unknown'
        else:
            # Use league mapper's classification logic
            full_label = self.league_mapper.classify_move(
                from_club=from_club,
                to_club=to_club,
                from_date=d0,
                to_date=d1
            )
            # Extract direction from label (e.g., "domestic_up" -> "up")
            if '_up' in full_label:
                move_dir = 'up'
            elif '_down' in full_label:
                move_dir = 'down'
            elif '_lateral' in full_label:
                move_dir = 'lateral'
            else:
                move_dir = 'unknown'
        
        # Compute normalized rates
        rate_per_30day = rate_per_day * 30
        
        # Get position group and age band
        position_group = self._get_position_group(position)
        age_band = self._get_age_band(age_at_d0)
        
        return TransitionRow(
            player_id=player_tm_id,
            age_at_d0=round(age_at_d0, 2),
            position=position,
            position_group=position_group,
            age_band=age_band,
            moved=moved,
            move_dir=move_dir,
            mapping_ok=mapping_ok,
            d0=d0_str,
            d1=d1_str,
            dt_days=dt_days,
            log_return=round(log_return, 6),
            rate_per_day=round(rate_per_day, 8),
            rate_per_30day=round(rate_per_30day, 6),
            v0=round(v0, 3),
            v1=round(v1, 3),
            from_club=from_club,
            to_club=to_club,
            from_tier=from_tier,
            to_tier=to_tier,
            from_mass=round(from_mass, 2) if from_mass else None,
            to_mass=round(to_mass, 2) if to_mass else None
        )
    
    def _load_player_data(self, player_tm_id: str) -> Optional[Dict]:
        """Load player data from enriched profile file."""
        data_dir = Path("data/extracted")
        
        # Find most recent enriched profile file
        profile_files = list(data_dir.glob("player_profile_*_enriched.jsonl"))
        if not profile_files:
            return None
        
        latest_file = max(profile_files, key=lambda p: p.stat().st_mtime)
        
        # Search for player
        with open(latest_file, 'r') as f:
            for line in f:
                record = json.loads(line)
                player_info = record.get('data', {}).get('player', {})
                if player_info.get('tm_id') == player_tm_id:
                    return record
        
        return None
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_str:
            return None
        
        # Try multiple formats
        formats = [
            '%Y-%m-%d',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%f',
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.split('+')[0].split('Z')[0], fmt)
            except ValueError:
                continue
        
        return None
