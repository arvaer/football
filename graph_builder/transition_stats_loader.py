"""
Loader for transition data and stratum statistics.

Provides singleton access to pre-computed transition records and
stratified statistics for dashboard and analysis use.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class StratumStats:
    """Statistics for a particular stratum (age_band, position, move_label)."""
    stratum_key: str
    age_band: str
    position: str
    move_label: str
    n: int
    mu_log_return: float
    sigma_log_return: float
    median_log_return: float
    mu_rate_per_day: float
    sigma_rate_per_day: float
    median_rate_per_day: float
    mu_rate_per_30day: float
    sigma_rate_per_30day: float
    median_rate_per_30day: float
    dt_days_median: int
    dt_days_mean: float
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'StratumStats':
        """Create from dictionary."""
        return cls(
            stratum_key=data['stratum_key'],
            age_band=data['age_band'],
            position=data['position'],
            move_label=data['move_label'],
            n=data['n'],
            mu_log_return=data['mu_log_return'],
            sigma_log_return=data['sigma_log_return'],
            median_log_return=data['median_log_return'],
            mu_rate_per_day=data['mu_rate_per_day'],
            sigma_rate_per_day=data['sigma_rate_per_day'],
            median_rate_per_day=data['median_rate_per_day'],
            mu_rate_per_30day=data.get('mu_rate_per_30day', data['mu_rate_per_day'] * 30),
            sigma_rate_per_30day=data.get('sigma_rate_per_30day', data['sigma_rate_per_day'] * 30),
            median_rate_per_30day=data.get('median_rate_per_30day', data['median_rate_per_day'] * 30),
            dt_days_median=data['dt_days_median'],
            dt_days_mean=data['dt_days_mean'],
        )


class TransitionStatsLoader:
    """
    Singleton loader for transition data and statistics.
    
    Lazy loads transition records and stratum statistics from disk.
    Provides quick lookup methods for dashboard and analysis.
    """
    
    _instance: Optional['TransitionStatsLoader'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._transitions: Optional[List[Dict]] = None
            self._transitions_by_player: Optional[Dict[str, List[Dict]]] = None
            self._stratum_stats: Optional[Dict[str, StratumStats]] = None
            TransitionStatsLoader._initialized = True
    
    def _load_transitions(self):
        """Lazy load transitions from most recent file."""
        if self._transitions is not None:
            return
        
        data_dir = Path("data/extracted")
        transition_files = list(data_dir.glob("mv_transitions_*.jsonl"))
        
        if not transition_files:
            print("Warning: No transition files found")
            self._transitions = []
            self._transitions_by_player = {}
            return
        
        latest_file = max(transition_files, key=lambda p: p.stat().st_mtime)
        print(f"Loading transitions from {latest_file.name}")
        
        self._transitions = []
        self._transitions_by_player = {}
        
        with open(latest_file, 'r') as f:
            for line in f:
                trans = json.loads(line)
                self._transitions.append(trans)
                
                # Index by player
                player_id = trans.get('player_id')
                if player_id:
                    if player_id not in self._transitions_by_player:
                        self._transitions_by_player[player_id] = []
                    self._transitions_by_player[player_id].append(trans)
        
        print(f"Loaded {len(self._transitions)} transitions for {len(self._transitions_by_player)} players")
    
    def _load_stratum_stats(self):
        """Lazy load stratum statistics from most recent file."""
        if self._stratum_stats is not None:
            return
        
        data_dir = Path("data/extracted")
        stats_files = list(data_dir.glob("stratum_stats_*.jsonl"))
        
        if not stats_files:
            print("Warning: No stratum stats files found")
            self._stratum_stats = {}
            return
        
        latest_file = max(stats_files, key=lambda p: p.stat().st_mtime)
        print(f"Loading stratum stats from {latest_file.name}")
        
        self._stratum_stats = {}
        
        with open(latest_file, 'r') as f:
            for line in f:
                stat_dict = json.loads(line)
                stat = StratumStats.from_dict(stat_dict)
                self._stratum_stats[stat.stratum_key] = stat
        
        print(f"Loaded {len(self._stratum_stats)} stratum statistics")
    
    def get_player_transitions(self, player_id: str) -> List[Dict]:
        """
        Get all transitions for a specific player.
        
        Args:
            player_id: Transfermarkt player ID
        
        Returns:
            List of transition dictionaries (empty if player not found)
        """
        self._load_transitions()
        return self._transitions_by_player.get(player_id, [])
    
    def get_stratum_stats(self, age: float, position: str, move_label: str) -> Optional[StratumStats]:
        """
        Get statistics for a specific stratum.
        
        Args:
            age: Player age (will be converted to age band)
            position: Player position
            move_label: Move classification label
        
        Returns:
            StratumStats if found, None otherwise
        """
        self._load_stratum_stats()
        
        # Convert age to band (U21, 21-24, 25-28, 29+)
        if age < 21:
            age_band = 'U21'
        elif age < 25:
            age_band = '21-24'
        elif age < 29:
            age_band = '25-28'
        else:
            age_band = '29+'
        
        stratum_key = f"{age_band}_{position}_{move_label}"
        return self._stratum_stats.get(stratum_key)
    
    def get_stratum_stats_by_key(self, stratum_key: str) -> Optional[StratumStats]:
        """Get statistics by full stratum key."""
        self._load_stratum_stats()
        return self._stratum_stats.get(stratum_key)
    
    def get_all_transitions(self) -> List[Dict]:
        """Get all loaded transitions."""
        self._load_transitions()
        return self._transitions or []
    
    def get_all_stratum_stats(self) -> Dict[str, StratumStats]:
        """Get all loaded stratum statistics."""
        self._load_stratum_stats()
        return self._stratum_stats or {}
    
    def reload(self):
        """Force reload of all data from disk."""
        self._transitions = None
        self._transitions_by_player = None
        self._stratum_stats = None
        self._load_transitions()
        self._load_stratum_stats()


# Singleton instance accessor
def get_transition_stats_loader() -> TransitionStatsLoader:
    """Get the singleton TransitionStatsLoader instance."""
    return TransitionStatsLoader()
