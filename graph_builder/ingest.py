"""
Data ingestion layer for loading scraped football data.

This module provides a clean interface to load data from JSONL files.
Design principle: Easy to swap JSONL source with database later.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional, Set
from dataclasses import dataclass
from datetime import datetime
import re

# LLM-based normalization cache (lazy-loaded)
_llm_normalization_cache: Optional[Dict[str, str]] = None


# LLM-based normalization cache (lazy-loaded)
_llm_normalization_cache: Optional[Dict[str, str]] = None


def load_llm_normalization_cache() -> Dict[str, str]:
    """
    Load the LLM-generated club normalization cache if available.
    
    Returns empty dict if cache file doesn't exist.
    """
    global _llm_normalization_cache
    
    if _llm_normalization_cache is not None:
        return _llm_normalization_cache
    
    cache_file = Path("data/club_normalization_cache.json")
    
    if not cache_file.exists():
        _llm_normalization_cache = {}
        return _llm_normalization_cache
    
    try:
        with open(cache_file, 'r') as f:
            _llm_normalization_cache = json.load(f)
        print(f"Loaded LLM club normalization cache: {len(_llm_normalization_cache)} entries")
        return _llm_normalization_cache
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to load normalization cache: {e}")
        _llm_normalization_cache = {}
        return _llm_normalization_cache


def clean_club_name(name: Optional[str]) -> Optional[str]:
    """
    Normalize club names for consistency.
    
    Args:
        name: Raw club name
    
    Returns:
        Cleaned club name or None
    """
    if not name or not isinstance(name, str):
        return None
    
    # Strip whitespace
    name = name.strip()
    
    if not name or name.lower() in ['unknown', 'none', 'n/a', '-']:
        return None
    
    # Common normalizations
    normalizations = {
        'Man United': 'Manchester United',
        'Man City': 'Manchester City',
        'Man Utd': 'Manchester United',
        'Napoli': 'SSC Napoli',
        'Inter': 'Inter Milan',
        'Inter Milano': 'Inter Milan',
        'Juve': 'Juventus FC',
        'Juventus': 'Juventus FC',
        'Barca': 'FC Barcelona',
        'Barça': 'FC Barcelona',
        'Bayern': 'Bayern Munich',
        'FC Bayern': 'Bayern Munich',
        'PSG': 'Paris Saint-Germain',
        'Paris SG': 'Paris Saint-Germain',
        'Tottenham': 'Tottenham Hotspur',
        'Spurs': 'Tottenham Hotspur',
        'Leicester': 'Leicester City',
        'Wolves': 'Wolverhampton',
        'Newcastle': 'Newcastle United',
        'West Ham': 'West Ham United',
        'Everton FC': 'Everton',
        'Leeds': 'Leeds United',
        'Brighton': 'Brighton & Hove Albion',
        'West Brom': 'West Bromwich Albion',
        'Norwich': 'Norwich City',
    }
    
    # Check for exact match in normalizations
    if name in normalizations:
        name = normalizations[name]
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name)
    
    # First, check LLM normalization cache
    llm_cache = load_llm_normalization_cache()
    if name in llm_cache:
        return llm_cache[name]
    
    return name


def clean_player_name(name: Optional[str]) -> Optional[str]:
    """Clean and normalize player names."""
    if not name or not isinstance(name, str):
        return None
    
    name = name.strip()
    
    if not name or name.lower() in ['unknown', 'none', 'n/a']:
        return None
    
    # Remove extra whitespace
    name = re.sub(r'\s+', ' ', name)
    
    # Remove common encoding artifacts
    name = name.replace('Ã­', 'í')
    name = name.replace('Ã©', 'é')
    name = name.replace('Ã³', 'ó')
    name = name.replace('Ã±', 'ñ')
    name = name.replace('Ã§', 'ç')
    
    return name


def normalize_position(position: Optional[str]) -> Optional[str]:
    """
    Normalize position codes to consistent categories.
    
    Returns position group: GK, DEF, MID, FWD or specific position if valid.
    """
    if not position or not isinstance(position, str):
        return None
    
    position = position.strip().upper()
    
    # Goalkeeper
    if position in ['GK', 'GOALKEEPER']:
        return 'GK'
    
    # Defenders
    if position in ['CB', 'LB', 'RB', 'LWB', 'RWB', 'SW', 'DEF', 'DEFENDER']:
        return position if position in ['CB', 'LB', 'RB', 'LWB', 'RWB'] else 'CB'
    
    # Midfielders
    if position in ['CM', 'DM', 'AM', 'LM', 'RM', 'CDM', 'CAM', 'MID', 'MIDFIELDER']:
        return position if position in ['CM', 'DM', 'AM', 'LM', 'RM'] else 'CM'
    
    # Forwards
    if position in ['LW', 'RW', 'CF', 'ST', 'SS', 'FWD', 'FORWARD', 'WINGER', 'STRIKER']:
        return position if position in ['LW', 'RW', 'CF', 'ST'] else 'CF'
    
    # Unknown positions
    return None


def clean_nationality(nationality: Optional[str]) -> Optional[str]:
    """
    Clean and normalize nationality strings.
    
    Handles multiple nationalities, keeps primary (first listed).
    """
    if not nationality or not isinstance(nationality, str):
        return None
    
    nationality = nationality.strip()
    
    if not nationality or nationality.lower() in ['unknown', 'none', 'n/a']:
        return None
    
    # Handle multiple nationalities (e.g., "Scotland, England")
    # Keep primary (first one)
    if ',' in nationality:
        parts = nationality.split(',')
        nationality = parts[0].strip()
    
    # Normalize common country name variations
    normalizations = {
        'England': 'England',
        'Scotland': 'Scotland',
        'Wales': 'Wales',
        'Northern Ireland': 'Northern Ireland',
        'Republic of Ireland': 'Ireland',
        'Cote d\'Ivoire': 'Ivory Coast',
        'Côte d\'Ivoire': 'Ivory Coast',
    }
    
    nationality = normalizations.get(nationality, nationality)
    
    return nationality


def validate_date(date_str: Optional[str]) -> Optional[str]:
    """
    Validate and normalize date strings.
    
    Accepts formats: YYYY-MM-DD, YYYY-MM-DDTHH:MM:SS
    Returns: YYYY-MM-DD or None
    """
    if not date_str or not isinstance(date_str, str):
        return None
    
    # Remove timestamp if present
    if 'T' in date_str:
        date_str = date_str.split('T')[0]
    
    # Validate format YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
        try:
            # Parse to ensure it's a valid date
            year, month, day = map(int, date_str.split('-'))
            if 1900 <= year <= 2020 and 1 <= month <= 12 and 1 <= day <= 31:
                return date_str
        except ValueError:
            pass
    
    return None


def validate_height(height_cm: Optional[int]) -> Optional[int]:
    """Validate player height in cm."""
    if height_cm is None:
        return None
    
    try:
        height_cm = int(height_cm)
        # Reasonable range for professional footballers: 150-220 cm
        if 150 <= height_cm <= 220:
            return height_cm
    except (ValueError, TypeError):
        pass
    
    return None


def validate_fee(amount: Optional[float]) -> Optional[float]:
    """Validate and clean fee amounts."""
    if amount is None:
        return None
    
    try:
        amount = float(amount)
        # Fee should be non-negative and reasonable (< 500M EUR)
        if amount < 0 or amount > 500:
            return None
        return round(amount, 2)
    except (ValueError, TypeError):
        return None


@dataclass
class Player:
    """Player entity."""
    tm_id: str
    name: str
    date_of_birth: Optional[str]
    nationality: Optional[str]
    position: Optional[str]
    current_club: Optional[str]
    scraped_at: str


@dataclass
class Transfer:
    """Transfer edge with attributes."""
    player_tm_id: str
    player_name: str
    from_club: Optional[str]
    to_club: Optional[str]
    transfer_date: Optional[str]
    season: Optional[str]
    transfer_type: str
    fee_amount: Optional[float]
    fee_currency: Optional[str]
    is_disclosed: bool
    has_addons: bool
    is_loan_fee: bool
    notes: Optional[str]
    market_value_at_transfer: Optional[float]
    source_url: str
    scraped_at: str


class DataSource:
    """
    Abstract data source interface.
    
    Future: Swap this with DatabaseSource, APISource, etc.
    without changing downstream code.
    """
    
    def load_players(self) -> List[Player]:
        """Load all players."""
        raise NotImplementedError
    
    def load_transfers(self) -> List[Transfer]:
        """Load all transfers."""
        raise NotImplementedError
    
    def get_club_lookup(self) -> Dict[str, str]:
        """
        Build club name normalization lookup.
        
        Returns dict mapping various club name variants to canonical name.
        For v0, we use simple exact match. Future: fuzzy matching, manual overrides.
        """
        raise NotImplementedError


class JSONLDataSource(DataSource):
    """Load data from JSONL files (current scraper output format)."""
    
    def __init__(self, data_dir: str = "data/extracted"):
        self.data_dir = Path(data_dir)
    
    def load_players(self) -> List[Player]:
        """Load players from player_profile JSONL files."""
        players = []
        seen_ids = set()
        skipped_count = {'no_id': 0, 'duplicate': 0, 'no_name': 0, 'invalid_data': 0}
        
        for jsonl_file in self.data_dir.glob("player_profile_*.jsonl"):
            with open(jsonl_file, 'r') as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if not record.get('success'):
                            continue
                        
                        # Each record has a 'data' field with player info
                        data = record.get('data', {})
                        tm_id = data.get('tm_id')
                        
                        # Skip if no ID
                        if not tm_id:
                            skipped_count['no_id'] += 1
                            continue
                        
                        # Skip duplicates
                        if tm_id in seen_ids:
                            skipped_count['duplicate'] += 1
                            continue
                        
                        # Clean player name
                        name = clean_player_name(data.get('name'))
                        if not name:
                            skipped_count['no_name'] += 1
                            continue
                        
                        # Clean and validate other fields
                        current_club = clean_club_name(data.get('current_club'))
                        nationality = clean_nationality(data.get('nationality'))
                        position = normalize_position(data.get('position'))
                        date_of_birth = validate_date(data.get('date_of_birth'))
                        height_cm = validate_height(data.get('height_cm'))
                        
                        # Get scraped_at timestamp
                        scraped_at = data.get('scraped_at', record.get('extracted_at', ''))
                        
                        players.append(Player(
                            tm_id=tm_id,
                            name=name,
                            date_of_birth=date_of_birth,
                            nationality=nationality,
                            position=position,
                            current_club=current_club,
                            scraped_at=scraped_at
                        ))
                        
                        seen_ids.add(tm_id)
                        
                    except (json.JSONDecodeError, KeyError, AttributeError) as e:
                        skipped_count['invalid_data'] += 1
                        continue
        
        # Log summary stats (useful for debugging)
        total_skipped = sum(skipped_count.values())
        if total_skipped > 0:
            print(f"Player loading stats:")
            print(f"  - Loaded: {len(players)}")
            print(f"  - Skipped: {total_skipped}")
            for reason, count in skipped_count.items():
                if count > 0:
                    print(f"    - {reason}: {count}")
        
        return players
    
    def load_transfers(self) -> List[Transfer]:
        """Load transfers from club_transfers JSONL files."""
        transfers = []
        seen_transfers = set()  # Track duplicates
        
        # Check both data/extracted and data/extractedt directories
        for data_dir in [self.data_dir, Path("data/extractedt")]:
            if not data_dir.exists():
                continue
                
            for jsonl_file in data_dir.glob("club_transfers_*.jsonl"):
                with open(jsonl_file, 'r') as f:
                    for line in f:
                        try:
                            record = json.loads(line)
                            if not record.get('success'):
                                continue
                            
                            # Each record contains a 'transfers' list
                            for transfer_data in record.get('transfers', []):
                                # Validate required fields
                                player_tm_id = transfer_data.get('player_tm_id')
                                if not player_tm_id:
                                    continue
                                
                                # Clean player name
                                player_name = clean_player_name(transfer_data.get('player_name'))
                                if not player_name:
                                    continue
                                
                                # Clean club names
                                from_club = clean_club_name(transfer_data.get('from_club'))
                                to_club = clean_club_name(transfer_data.get('to_club'))
                                
                                # Skip if both clubs are None (invalid transfer)
                                if not from_club and not to_club:
                                    continue
                                
                                # Get fee data
                                fee = transfer_data.get('fee', {})
                                fee_amount = validate_fee(fee.get('amount'))
                                fee_currency = fee.get('currency', 'EUR')
                                
                                # Create unique transfer key for deduplication
                                transfer_key = (
                                    player_tm_id,
                                    from_club or '',
                                    to_club or '',
                                    transfer_data.get('season', ''),
                                    fee_amount or 0
                                )
                                
                                # Skip duplicates
                                if transfer_key in seen_transfers:
                                    continue
                                
                                transfers.append(Transfer(
                                    player_tm_id=player_tm_id,
                                    player_name=player_name,
                                    from_club=from_club,
                                    to_club=to_club,
                                    transfer_date=transfer_data.get('transfer_date'),
                                    season=transfer_data.get('season'),
                                    transfer_type=transfer_data.get('transfer_type', 'unknown'),
                                    fee_amount=fee_amount,
                                    fee_currency=fee_currency,
                                    is_disclosed=fee.get('is_disclosed', False),
                                    has_addons=fee.get('has_addons', False),
                                    is_loan_fee=fee.get('is_loan_fee', False),
                                    notes=fee.get('notes'),
                                    market_value_at_transfer=transfer_data.get('market_value_at_transfer'),
                                    source_url=transfer_data.get('source_url', ''),
                                    scraped_at=transfer_data.get('scraped_at', '')
                                ))
                                
                                seen_transfers.add(transfer_key)
                                
                        except (json.JSONDecodeError, KeyError) as e:
                            # Skip malformed records
                            continue
        
        return transfers
    
    def get_club_lookup(self) -> Dict[str, str]:
        """
        Build club name normalization from transfer data.
        
        Strategy: Use most common variant as canonical, map all variants to it.
        For v0: simple exact match. Future: add manual overrides, fuzzy matching.
        """
        from collections import Counter
        
        club_names: Set[str] = set()
        
        # Collect all unique club names
        transfers = self.load_transfers()
        for transfer in transfers:
            if transfer.from_club:
                club_names.add(transfer.from_club)
            if transfer.to_club:
                club_names.add(transfer.to_club)
        
        # For v0: identity mapping (each name maps to itself)
        # This preserves exact matches, prevents data loss
        lookup = {name: name for name in club_names if name}
        
        # Future enhancement: detect variants and map to canonical
        # e.g., {"Man United": "Manchester United", "Man Utd": "Manchester United"}
        
        return lookup


def get_data_source(source_type: str = "jsonl", **kwargs) -> DataSource:
    """
    Factory function to get appropriate data source.
    
    Args:
        source_type: "jsonl", "postgres", "api", etc.
        **kwargs: source-specific configuration
    
    Returns:
        DataSource instance
    
    Example:
        # Current usage
        source = get_data_source("jsonl", data_dir="data/extracted")
        
        # Future usage (when persistence layer added)
        source = get_data_source("postgres", connection_string="...")
    """
    if source_type == "jsonl":
        return JSONLDataSource(**kwargs)
    else:
        raise ValueError(f"Unknown source type: {source_type}")
