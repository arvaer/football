"""Init for extractors package."""

from scraper.extractors.utils import (
    extract_id_from_url,
    parse_money,
    normalize_position,
    normalize_transfer_type,
    clean_text,
    parse_date,
)

from scraper.extractors.transfermarkt_bs import (
    parse_player_profile,
    parse_player_transfers,
    parse_club_profile,
    parse_club_transfers,
    parse_competition_clubs,
)

__all__ = [
    'extract_id_from_url',
    'parse_money',
    'normalize_position',
    'normalize_transfer_type',
    'clean_text',
    'parse_date',
    'parse_player_profile',
    'parse_player_transfers',
    'parse_club_profile',
    'parse_club_transfers',
    'parse_competition_clubs',
]
