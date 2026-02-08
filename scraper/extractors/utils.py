"""Utility functions for parsing Transfermarkt HTML."""

import re
from typing import Optional, Tuple
from decimal import Decimal


def extract_id_from_url(url: str, entity_type: str) -> Optional[str]:
    """
    Extract canonical ID from Transfermarkt URL.
    
    Args:
        url: URL to parse
        entity_type: 'player', 'club', or 'league'
    
    Returns:
        ID string or None if not found
    
    Examples:
        /profil/spieler/418560 -> '418560'
        /spieler/418560 -> '418560'
        /startseite/verein/281 -> '281'
        /verein/281 -> '281'
        /wettbewerb/GB1 -> 'GB1'
    """
    patterns = {
        'player': [
            r'/profil/spieler/(\d+)',
            r'/spieler/(\d+)',
            r'/transfers/spieler/(\d+)',
        ],
        'club': [
            r'/startseite/verein/(\d+)',
            r'/verein/(\d+)',
            r'/transfers/verein/(\d+)',
        ],
        'league': [
            r'/wettbewerb/([A-Z0-9]+)',
        ],
    }
    
    for pattern in patterns.get(entity_type, []):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    return None


def parse_money(text: str) -> Tuple[Optional[float], str, bool]:
    """
    Parse money string into amount, currency, and disclosed status.
    
    Args:
        text: Money string to parse
    
    Returns:
        Tuple of (amount in millions, currency code, is_disclosed)
    
    Examples:
        '€15.5m' -> (15.5, 'EUR', True)
        '€500k' -> (0.5, 'EUR', True)
        '£20m' -> (20.0, 'GBP', True)
        '$10.5m' -> (10.5, 'USD', True)
        'free transfer' -> (None, 'EUR', False)
        'loan' -> (None, 'EUR', False)
        'undisclosed' -> (None, 'EUR', False)
        '-' -> (None, 'EUR', False)
    """
    if not text or not isinstance(text, str):
        return None, 'EUR', False
    
    text = text.strip().lower()
    
    # Handle special cases
    if text in ['free transfer', 'free', 'loan', 'end of loan', 'undisclosed', '-', '?', 'n/a']:
        return None, 'EUR', False
    
    # Determine currency
    currency = 'EUR'  # default
    if '£' in text or 'gbp' in text:
        currency = 'GBP'
    elif '$' in text or 'usd' in text:
        currency = 'USD'
    elif '€' in text or 'eur' in text:
        currency = 'EUR'
    
    # Extract numeric value
    # Remove currency symbols and text
    numeric_text = re.sub(r'[€£$]', '', text)
    numeric_text = re.sub(r'[a-z\s]+', '', numeric_text)
    
    # Match patterns like "15.5m", "500k", "2.87"
    match = re.search(r'([\d,]+\.?\d*)\s*([mk])?', numeric_text, re.IGNORECASE)
    
    if not match:
        return None, currency, False
    
    value_str = match.group(1).replace(',', '')
    unit = match.group(2)
    
    try:
        value = float(value_str)
        
        # Apply unit multiplier
        if unit and unit.lower() == 'k':
            value = value / 1000.0  # Convert to millions
        elif unit and unit.lower() == 'm':
            value = value  # Already in millions
        else:
            # No unit specified - assume raw value
            # If value is very large (> 1000), assume it's in base currency units
            if value > 1000:
                value = value / 1_000_000.0  # Convert to millions
        
        return value, currency, True
        
    except ValueError:
        return None, currency, False


def normalize_position(position: str) -> str:
    """
    Normalize position string to standard abbreviation.
    
    Args:
        position: Position string from Transfermarkt
    
    Returns:
        Normalized position code
    
    Examples:
        'Goalkeeper' -> 'GK'
        'Centre-Back' -> 'CB'
        'Defensive Midfield' -> 'DM'
        'Left Winger' -> 'LW'
    """
    if not position:
        return 'UNKNOWN'
    
    position = position.strip().lower()
    
    # Position mapping
    mapping = {
        'goalkeeper': 'GK',
        'centre-back': 'CB',
        'center back': 'CB',
        'defender': 'CB',
        'central defence': 'CB',
        'left-back': 'LB',
        'left back': 'LB',
        'right-back': 'RB',
        'right back': 'RB',
        'defensive midfield': 'DM',
        'defensive midfielder': 'DM',
        'central midfield': 'CM',
        'central midfielder': 'CM',
        'midfield': 'CM',
        'attacking midfield': 'AM',
        'attacking midfielder': 'AM',
        'left winger': 'LW',
        'left wing': 'LW',
        'right winger': 'RW',
        'right wing': 'RW',
        'centre-forward': 'CF',
        'center forward': 'CF',
        'striker': 'ST',
        'forward': 'ST',
        'attack': 'ST',
    }
    
    return mapping.get(position, 'UNKNOWN')


def normalize_transfer_type(transfer_type: str) -> str:
    """
    Normalize transfer type string.
    
    Args:
        transfer_type: Transfer type string from Transfermarkt
    
    Returns:
        Normalized transfer type
    
    Examples:
        'Transfer' -> 'permanent'
        'Loan' -> 'loan'
        'Free transfer' -> 'free'
        'End of loan' -> 'end_of_loan'
    """
    if not transfer_type:
        return 'unknown'
    
    transfer_type = transfer_type.strip().lower()
    
    mapping = {
        'transfer': 'permanent',
        'permanent': 'permanent',
        'loan': 'loan',
        'on loan': 'loan',
        'free transfer': 'free',
        'free': 'free',
        'end of loan': 'end_of_loan',
        'loan return': 'end_of_loan',
    }
    
    return mapping.get(transfer_type, 'unknown')


def clean_text(text: Optional[str]) -> Optional[str]:
    """Clean and normalize text."""
    if not text:
        return None
    
    # Strip whitespace
    text = text.strip()
    
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    
    # Remove invisible characters
    text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
    
    return text if text else None


def parse_date(date_str: str) -> Optional[str]:
    """
    Parse date string into ISO format.
    
    Args:
        date_str: Date string to parse
    
    Returns:
        ISO date string (YYYY-MM-DD) or None
    
    Examples:
        'Jan 1, 2023' -> '2023-01-01'
        '01.01.2023' -> '2023-01-01'
        '2023-01-01' -> '2023-01-01'
    """
    if not date_str:
        return None
    
    date_str = date_str.strip()
    
    # Try ISO format first
    if re.match(r'\d{4}-\d{2}-\d{2}', date_str):
        return date_str
    
    # Try DD.MM.YYYY format (common in Transfermarkt)
    match = re.match(r'(\d{1,2})\.(\d{1,2})\.(\d{4})', date_str)
    if match:
        day, month, year = match.groups()
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    
    # Try MMM DD, YYYY format
    month_names = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12',
    }
    
    match = re.match(r'([a-z]{3})\s+(\d{1,2}),\s+(\d{4})', date_str.lower())
    if match:
        month, day, year = match.groups()
        month_num = month_names.get(month)
        if month_num:
            return f"{year}-{month_num}-{day.zfill(2)}"
    
    return None
