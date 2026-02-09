"""BeautifulSoup-based deterministic extractors for Transfermarkt pages."""

import re
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup, Tag
import structlog

from scraper.extractors.utils import (
    extract_id_from_url,
    parse_money,
    normalize_position,
    normalize_transfer_type,
    clean_text,
    parse_date,
)

logger = structlog.get_logger()


class ExtractionError(Exception):
    """Raised when extraction fails."""
    pass


def parse_player_profile(html: str, url: str) -> Dict[str, Any]:
    """
    Parse player profile page using BeautifulSoup.
    
    Args:
        html: HTML content
        url: Page URL
    
    Returns:
        Dict matching Player schema
    
    Raises:
        ExtractionError: If required markers are missing or parsing fails
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Verify page markers
    if '/profil/spieler/' not in url and '/spieler/' not in url:
        raise ExtractionError(f"URL does not match player profile pattern: {url}")
    
    # Extract player ID from URL
    player_id = extract_id_from_url(url, 'player')
    if not player_id:
        raise ExtractionError(f"Could not extract player ID from URL: {url}")
    
    data = {
        "player": {
            "tm_id": player_id,
        }
    }
    
    # Extract player name from header
    # Transfermarkt uses h1.data-header__headline-wrapper or similar
    name_elem = soup.find('h1', class_='data-header__headline-wrapper')
    if not name_elem:
        # Fallback: try other common headers
        name_elem = soup.find('h1')
    
    if name_elem:
        # Get text, clean it
        name = clean_text(name_elem.get_text())
        # Sometimes name includes extra info in spans - get just the main text
        if name:
            # Remove extra whitespace
            name = re.sub(r'\s+', ' ', name).strip()
            data["player"]["name"] = name
    
    # Find info table with player details
    info_table = soup.find('div', class_='info-table')
    if not info_table:
        # Try alternate structure
        info_table = soup.find('table', class_='auflistung')
    
    if info_table:
        # Extract rows
        rows = info_table.find_all('tr') if info_table.name == 'table' else info_table.find_all(['div', 'span'])
        
        for i, row in enumerate(rows):
            # Get label and value
            label_elem = row.find(['th', 'span'], class_=re.compile(r'info-table__content--label'))
            value_elem = row.find(['td', 'span'], class_=re.compile(r'info-table__content--regular'))
            
            if not label_elem or not value_elem:
                continue
            
            label = clean_text(label_elem.get_text())
            value = clean_text(value_elem.get_text())
            
            if not label or not value:
                continue
            
            label_lower = label.lower()
            
            # Date of birth
            if 'date of birth' in label_lower or 'born' in label_lower:
                # Parse date
                parsed_date = parse_date(value)
                if parsed_date:
                    data["player"]["date_of_birth"] = parsed_date
            
            # Height
            elif 'height' in label_lower:
                # Extract number from "1.94 m" or "194 cm"
                match = re.search(r'(\d+)[.,]?(\d*)\s*(m|cm)', value.lower())
                if match:
                    whole = int(match.group(1))
                    decimal = match.group(2)
                    unit = match.group(3)
                    
                    if unit == 'm':
                        # Convert to cm
                        height_cm = whole * 100
                        if decimal:
                            height_cm += int(decimal) * 10
                    else:
                        height_cm = whole
                    
                    data["player"]["height_cm"] = height_cm
            
            # Position
            elif 'position' in label_lower:
                position = normalize_position(value)
                data["player"]["position"] = position
            
            # Foot
            elif 'foot' in label_lower:
                data["player"]["dominant_foot"] = value
            
            # Nationality
            elif 'citizen' in label_lower or 'nationality' in label_lower:
                data["player"]["nationality"] = value
            
            # Current club
            elif 'current club' in label_lower or 'club' in label_lower:
                # Extract just the club name, not the link
                club_link = value_elem.find('a')
                if club_link:
                    club_name = clean_text(club_link.get_text())
                    if club_name:
                        data["player"]["current_club"] = club_name
                else:
                    data["player"]["current_club"] = value
    
    # Market values (optional)
    data["market_values"] = []
    
    # Find market value chart or table
    # This is complex and varies - for now, extract current market value if present
    market_value_elem = soup.find('div', class_='tm-player-market-value-development__current-value')
    if market_value_elem:
        value_text = clean_text(market_value_elem.get_text())
        if value_text:
            amount, currency, is_disclosed = parse_money(value_text)
            if amount is not None:
                # Add to market values
                data["market_values"].append({
                    "value": amount,
                    "currency": currency,
                    "date": None,  # Would need to extract from chart
                    "club": data["player"].get("current_club"),
                })
    
    logger.info("bs_extraction_player_profile", player_id=player_id, fields=list(data["player"].keys()))
    
    return data


def parse_player_transfers(html: str, url: str) -> Dict[str, Any]:
    """
    Parse player transfers page using BeautifulSoup.
    
    Args:
        html: HTML content
        url: Page URL
    
    Returns:
        Dict matching Transfer schema
    
    Raises:
        ExtractionError: If required markers are missing or parsing fails
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Verify page markers
    if '/transfers/spieler/' not in url and '/spieler/' not in url:
        raise ExtractionError(f"URL does not match player transfers pattern: {url}")
    
    # Extract player ID from URL
    player_id = extract_id_from_url(url, 'player')
    if not player_id:
        raise ExtractionError(f"Could not extract player ID from URL: {url}")
    
    # Extract player name from header
    name_elem = soup.find('h1', class_='data-header__headline-wrapper')
    if not name_elem:
        name_elem = soup.find('h1')
    
    player_name = None
    if name_elem:
        player_name = clean_text(name_elem.get_text())
    
    data = {
        "player_tm_id": player_id,
        "player_name": player_name,
        "transfers": []
    }
    
    # Find transfer tables
    # Transfermarkt uses table.items for transfer tables
    tables = soup.find_all('table', class_='items')
    
    if not tables:
        logger.warning("bs_extraction_no_transfer_table", url=url)
        return data
    
    for table in tables:
        # Check if this is a transfer table (not stats or other data)
        # Transfer tables have specific headers
        thead = table.find('thead')
        if not thead:
            continue
        
        headers_text = clean_text(thead.get_text()).lower()
        if 'transfer' not in headers_text and 'date' not in headers_text:
            continue
        
        # Parse rows
        tbody = table.find('tbody')
        if not tbody:
            continue
        
        rows = tbody.find_all('tr', recursive=False)
        
        for row in rows:
            # Skip header rows or separators
            if row.find('th'):
                continue
            
            cells = row.find_all('td')
            if len(cells) < 5:
                continue
            
            transfer = {}
            
            # Typical structure:
            # 0: Season
            # 1: Date
            # 2: From club
            # 3: To club
            # 4: Market value
            # 5: Fee
            
            # Extract based on cell position and content
            for idx, cell in enumerate(cells):
                cell_text = clean_text(cell.get_text())
                
                # Season (usually first column)
                if idx == 0 and '/' in cell_text:
                    transfer["season"] = cell_text
                
                # Date
                elif 'date' in cell.get('class', []) or (idx == 1 and re.match(r'\w{3}\s+\d{1,2},\s+\d{4}', cell_text or '')):
                    parsed_date = parse_date(cell_text)
                    if parsed_date:
                        transfer["transfer_date"] = parsed_date
                
                # From club
                elif 'club-from' in ' '.join(cell.get('class', [])):
                    club_link = cell.find('a', href=re.compile(r'/verein/'))
                    if club_link:
                        transfer["from_club"] = clean_text(club_link.get_text())
                        from_club_id = extract_id_from_url(club_link['href'], 'club')
                        if from_club_id:
                            transfer["from_club_tm_id"] = from_club_id
                
                # To club
                elif 'club-to' in ' '.join(cell.get('class', [])):
                    club_link = cell.find('a', href=re.compile(r'/verein/'))
                    if club_link:
                        transfer["to_club"] = clean_text(club_link.get_text())
                        to_club_id = extract_id_from_url(club_link['href'], 'club')
                        if to_club_id:
                            transfer["to_club_tm_id"] = to_club_id
                
                # Market value at transfer
                elif 'market-value' in ' '.join(cell.get('class', [])):
                    amount, currency, is_disclosed = parse_money(cell_text)
                    if amount is not None:
                        transfer["market_value_at_transfer"] = amount
                
                # Fee
                elif 'fee' in ' '.join(cell.get('class', [])) or idx >= 5:
                    # Parse fee
                    amount, currency, is_disclosed = parse_money(cell_text)
                    
                    # Determine transfer type
                    cell_text_lower = (cell_text or '').lower()
                    if 'loan' in cell_text_lower:
                        transfer_type = 'loan'
                        is_loan_fee = True
                    elif 'free' in cell_text_lower:
                        transfer_type = 'free'
                        is_loan_fee = False
                    elif 'end of loan' in cell_text_lower:
                        transfer_type = 'end_of_loan'
                        is_loan_fee = False
                    else:
                        transfer_type = 'permanent'
                        is_loan_fee = False
                    
                    transfer["transfer_type"] = transfer_type
                    transfer["fee"] = {
                        "amount": amount,
                        "currency": currency,
                        "is_disclosed": is_disclosed,
                        "is_loan_fee": is_loan_fee,
                        "notes": cell_text if not is_disclosed else None,
                    }
            
            # Only add if we have some data
            if transfer:
                data["transfers"].append(transfer)
    
    logger.info("bs_extraction_player_transfers", player_id=player_id, transfers=len(data["transfers"]))
    
    return data


def parse_club_transfers(html: str, url: str) -> Dict[str, Any]:
    """
    Parse club transfers page using BeautifulSoup.
    
    Args:
        html: HTML content
        url: Page URL
    
    Returns:
        Dict matching Transfer schema for club
    
    Raises:
        ExtractionError: If required markers are missing or parsing fails
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Verify page markers
    if '/transfers/verein/' not in url and '/verein/' not in url:
        raise ExtractionError(f"URL does not match club transfers pattern: {url}")
    
    # Extract club ID from URL
    club_id = extract_id_from_url(url, 'club')
    if not club_id:
        raise ExtractionError(f"Could not extract club ID from URL: {url}")
    
    # Extract club name from header
    name_elem = soup.find('h1', class_='data-header__headline-wrapper')
    if not name_elem:
        name_elem = soup.find('h1')
    
    club_name = None
    if name_elem:
        club_name = clean_text(name_elem.get_text())
    
    # Extract season from page (if shown)
    season = None
    season_elem = soup.find('select', {'name': 'saison_id'})
    if season_elem:
        selected = season_elem.find('option', selected=True)
        if selected:
            season = clean_text(selected.get_text())
    
    data = {
        "club_tm_id": club_id,
        "club_name": club_name,
        "season": season,
        "transfers": []
    }
    
    # Find transfer tables
    # Club transfers page has both arrivals and departures in responsive-table divs
    # Look for all tables with class='items' inside responsive-table containers
    
    responsive_tables = soup.find_all('div', class_='responsive-table')
    
    if not responsive_tables:
        logger.warning("bs_extraction_no_responsive_table", url=url)
        return data
    
    for responsive_div in responsive_tables:
        # Find the table
        table = responsive_div.find('table', class_='items')
        if not table:
            continue
        
        # Determine if this is arrivals or departures from the thead
        thead = table.find('thead')
        if not thead:
            continue
        
        # Check headers to determine transfer direction
        # Arrivals have "Joined" column, Departures have "Left" column
        headers = thead.find_all('th')
        header_texts = [clean_text(th.get_text()).lower() if th.get_text() else '' for th in headers]
        
        is_arrivals = any('join' in h for h in header_texts)
        is_departures = any('left' in h for h in header_texts)
        
        if not (is_arrivals or is_departures):
            # Can't determine direction, skip
            continue
        
        # Parse rows
        tbody = table.find('tbody')
        if not tbody:
            continue
        
        rows = tbody.find_all('tr', recursive=False)
        
        for row in rows:
            # Skip header rows or separators
            if row.find('th'):
                continue
            
            cells = row.find_all('td')
            if len(cells) < 4:
                continue
            
            transfer = {}
            
            # Typical structure for club transfers:
            # cells[0]: Position badge
            # cells[1]: Player info (nested table with name, image, position)
            # cells[2]: Age
            # cells[3]: Nationality
            # cells[4]: Club info (other club + league)
            # cells[5]: Fee
            
            # Extract player from cells[1]
            player_cell = cells[1] if len(cells) > 1 else None
            if player_cell:
                player_link = player_cell.find('a', href=re.compile(r'/spieler/'))
                if player_link:
                    transfer["player_name"] = clean_text(player_link.get_text())
                    player_id = extract_id_from_url(player_link.get('href', ''), 'player')
                    if player_id:
                        transfer["player_tm_id"] = player_id
            
            # Extract other club from cells[4]
            club_cell = cells[4] if len(cells) > 4 else None
            if club_cell:
                club_link = club_cell.find('a', href=re.compile(r'/verein/'))
                if club_link:
                    other_club_name = clean_text(club_link.get_text())
                    other_club_id = extract_id_from_url(club_link.get('href', ''), 'club')
                    
                    if is_arrivals:
                        # Player joined from other club
                        transfer["from_club"] = other_club_name
                        if other_club_id:
                            transfer["from_club_tm_id"] = other_club_id
                        transfer["to_club"] = club_name
                        if club_id:
                            transfer["to_club_tm_id"] = club_id
                    else:
                        # Player left to other club
                        transfer["to_club"] = other_club_name
                        if other_club_id:
                            transfer["to_club_tm_id"] = other_club_id
                        transfer["from_club"] = club_name
                        if club_id:
                            transfer["from_club_tm_id"] = club_id
            
            # Extract fee from cells[5] (last cell)
            fee_cell = cells[5] if len(cells) > 5 else cells[-1]
            if fee_cell:
                fee_text = clean_text(fee_cell.get_text())
                if fee_text:
                    amount, currency, is_disclosed = parse_money(fee_text)
                    
                    transfer["fee"] = {
                        "amount": amount,
                        "currency": currency,
                        "is_disclosed": is_disclosed,
                        "notes": fee_text if not is_disclosed or amount is None else None,
                    }
            
            # Only add if we have player info
            if "player_name" in transfer or "player_tm_id" in transfer:
                data["transfers"].append(transfer)
    
    logger.info("bs_extraction_club_transfers", club_id=club_id, transfers=len(data["transfers"]))
    
    return data


def parse_club_profile(html: str, url: str) -> Dict[str, Any]:
    """
    Parse club profile page using BeautifulSoup.
    
    Args:
        html: HTML content
        url: Page URL
    
    Returns:
        Dict matching Club schema
    
    Raises:
        ExtractionError: If required markers are missing or parsing fails
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Verify page markers
    if '/startseite/verein/' not in url and '/verein/' not in url:
        raise ExtractionError(f"URL does not match club profile pattern: {url}")
    
    # Extract club ID from URL
    club_id = extract_id_from_url(url, 'club')
    if not club_id:
        raise ExtractionError(f"Could not extract club ID from URL: {url}")
    
    data = {
        "club": {
            "tm_id": club_id,
        }
    }
    
    # Extract club name from header
    name_elem = soup.find('h1', class_='data-header__headline-wrapper')
    if not name_elem:
        name_elem = soup.find('h1')
    
    if name_elem:
        name = clean_text(name_elem.get_text())
        if name:
            data["club"]["name"] = name
    
    # Find info table with club details
    info_table = soup.find('div', class_='info-table')
    if not info_table:
        info_table = soup.find('table', class_='auflistung')
    
    if info_table:
        rows = info_table.find_all('tr') if info_table.name == 'table' else info_table.find_all(['div', 'span'])
        
        for row in rows:
            label_elem = row.find(['th', 'span'], class_=re.compile(r'info-table__content--label'))
            value_elem = row.find(['td', 'span'], class_=re.compile(r'info-table__content--regular'))
            
            if not label_elem or not value_elem:
                continue
            
            label = clean_text(label_elem.get_text())
            value = clean_text(value_elem.get_text())
            
            if not label or not value:
                continue
            
            label_lower = label.lower()
            
            # Country
            if 'country' in label_lower:
                data["club"]["country"] = value
            
            # League
            elif 'league' in label_lower or 'competition' in label_lower:
                league_link = value_elem.find('a')
                if league_link:
                    league_name = clean_text(league_link.get_text())
                    if league_name:
                        data["club"]["league"] = league_name
                else:
                    data["club"]["league"] = value
            
            # Division / Tier
            elif 'tier' in label_lower or 'division' in label_lower:
                # Extract number
                match = re.search(r'\d+', value)
                if match:
                    data["club"]["division"] = int(match.group())
    
    logger.info("bs_extraction_club_profile", club_id=club_id, fields=list(data["club"].keys()))
    
    return data


def parse_competition_clubs(html: str, url: str) -> Dict[str, Any]:
    """
    Parse competition page club statistics table using BeautifulSoup.
    
    Extracts all clubs in a competition with their squad statistics including:
    - Squad size
    - Average age
    - Number of foreigners
    - Average market value per player
    - Total market value
    - Summary row totals
    
    Args:
        html: HTML content
        url: Page URL (e.g., /major-league-soccer/startseite/wettbewerb/MLS1)
    
    Returns:
        Dict with competition info, list of club stats, and summary
    
    Raises:
        ExtractionError: If required markers are missing or parsing fails
    """
    soup = BeautifulSoup(html, 'html.parser')
    
    # Verify page markers
    if '/wettbewerb/' not in url:
        raise ExtractionError(f"URL does not match competition pattern: {url}")
    
    # Extract competition code from URL
    competition_code = None
    match = re.search(r'/wettbewerb/([A-Z0-9]+)', url)
    if match:
        competition_code = match.group(1)
    
    # Extract competition name from header
    competition_name = None
    name_elem = soup.find('h1', class_='data-header__headline-wrapper')
    if name_elem:
        competition_name = clean_text(name_elem.get_text())
    
    data = {
        "competition": {
            "code": competition_code,
            "name": competition_name,
            "url": url,
        },
        "clubs": [],
        "summary": {}
    }
    
    # Find the responsive-table containing club statistics
    # The table typically has columns: Club, Squad, ø age, Foreigners, ø market value, Total market value
    responsive_tables = soup.find_all('div', class_='responsive-table')
    
    clubs_table = None
    for table_div in responsive_tables:
        table = table_div.find('table', class_='items')
        if not table:
            continue
        
        # Check if this is the clubs table by looking at headers
        thead = table.find('thead')
        if thead:
            headers = thead.find_all('th')
            header_texts = [clean_text(th.get_text()).lower() for th in headers]
            
            # Look for characteristic columns like "squad", "market value", etc.
            if any('squad' in h for h in header_texts) or any('market value' in h for h in header_texts):
                clubs_table = table
                break
    
    if not clubs_table:
        logger.warning("bs_extraction_no_clubs_table", url=url)
        return data
    
    # Parse table headers to understand column positions
    thead = clubs_table.find('thead')
    if not thead:
        raise ExtractionError("No thead found in clubs table")
    
    headers = thead.find_all('th')
    header_map = {}
    col_offset = 0  # Track offset for colspan columns
    
    for idx, th in enumerate(headers):
        header_text = clean_text(th.get_text()).lower()
        colspan = int(th.get('colspan', 1))
        
        # Check if this header is hidden (won't appear as a cell in tbody)
        th_classes = th.get('class', [])
        is_hidden = 'hide' in th_classes
        
        if 'club' in header_text:
            # Club column typically spans 2 cells (logo + name)
            header_map['club_img'] = col_offset
            header_map['club_name'] = col_offset + 1 if colspan > 1 else col_offset
        elif not is_hidden:
            # Only map non-hidden columns to cell positions
            if 'squad' in header_text:
                header_map['squad'] = col_offset
            elif 'age' in header_text or 'ø age' in header_text:
                header_map['avg_age'] = col_offset
            elif 'foreigner' in header_text:
                header_map['foreigners'] = col_offset
            elif 'ø market value' in header_text or header_text == 'ø market value':
                header_map['avg_market_value'] = col_offset
            elif 'total market value' in header_text:
                header_map['total_market_value'] = col_offset
        
        # Only increment col_offset if not hidden
        if not is_hidden:
            col_offset += colspan
    
    logger.debug("clubs_table_headers", header_map=header_map)
    
    # Parse tbody rows
    tbody = clubs_table.find('tbody')
    if not tbody:
        raise ExtractionError("No tbody found in clubs table")
    
    rows = tbody.find_all('tr', recursive=False)
    
    for row in rows:
        # Check if this is a summary row (typically has class or different structure)
        row_classes = row.get('class', [])
        is_summary = 'footer' in ' '.join(row_classes) or 'summe' in ' '.join(row_classes)
        
        cells = row.find_all('td')
        if len(cells) < 2:
            continue
        
        # Extract club information
        club_data = {}
        
        # Extract club name from the club_name cell
        if 'club_name' in header_map:
            idx = header_map['club_name']
            if idx < len(cells):
                cell = cells[idx]
                # Look for club link in this cell
                club_link = cell.find('a', href=re.compile(r'/verein/'))
                if club_link:
                    club_data['name'] = clean_text(club_link.get_text())
                    club_id = extract_id_from_url(club_link.get('href', ''), 'club')
                    if club_id:
                        club_data['tm_id'] = club_id
                else:
                    # For summary rows or cells without links
                    club_data['name'] = clean_text(cell.get_text())
        
        # Extract other stats
        for col_name, idx in header_map.items():
            if col_name in ['club_img', 'club_name']:
                continue  # Already handled
            
            if idx >= len(cells):
                continue
            
            cell = cells[idx]
            cell_text = clean_text(cell.get_text())
            
            if col_name == 'squad':
                # Parse squad size as integer
                if cell_text:
                    try:
                        club_data['squad_size'] = int(cell_text.replace(',', ''))
                    except ValueError:
                        club_data['squad_size'] = None
            
            elif col_name == 'avg_age':
                # Parse average age as float
                if cell_text:
                    try:
                        # Format is usually like "25.7" or "25.4 Years"
                        age_str = cell_text.replace('Years', '').replace(',', '.').strip()
                        club_data['average_age'] = float(age_str)
                    except ValueError:
                        club_data['average_age'] = None
            
            elif col_name == 'foreigners':
                # Parse foreigners count as integer
                if cell_text:
                    try:
                        club_data['foreigners'] = int(cell_text.replace(',', ''))
                    except ValueError:
                        club_data['foreigners'] = None
            
            elif col_name == 'avg_market_value':
                # Parse market value (e.g., "€112k", "€1.2m")
                amount, currency, _ = parse_money(cell_text)
                if amount is not None:
                    club_data['average_market_value'] = amount
                    club_data['average_market_value_currency'] = currency
            
            elif col_name == 'total_market_value':
                # Parse total market value (e.g., "€3.48m", "€100.5m")
                amount, currency, _ = parse_money(cell_text)
                if amount is not None:
                    club_data['total_market_value'] = amount
                    club_data['total_market_value_currency'] = currency
        
        # Add to appropriate list
        if is_summary:
            data['summary'] = club_data
            logger.debug("extracted_summary", summary=club_data)
        else:
            if club_data:  # Only add if we extracted something
                data['clubs'].append(club_data)
    
    # Also check tfoot for summary row
    tfoot = clubs_table.find('tfoot')
    if tfoot and not data['summary']:
        footer_row = tfoot.find('tr')
        if footer_row:
            cells = footer_row.find_all('td')
            if len(cells) >= 2:
                summary_data = {}
                
                # Extract stats from footer (usually aligned with body columns)
                for col_name, idx in header_map.items():
                    if col_name in ['club_img', 'club_name']:
                        continue
                    
                    if idx >= len(cells):
                        continue
                    
                    cell = cells[idx]
                    cell_text = clean_text(cell.get_text())
                    
                    if col_name == 'squad':
                        try:
                            summary_data['squad_size'] = int(cell_text.replace(',', ''))
                        except ValueError:
                            pass
                    elif col_name == 'avg_age':
                        try:
                            age_str = cell_text.replace('Years', '').replace(',', '.').strip()
                            summary_data['average_age'] = float(age_str)
                        except ValueError:
                            pass
                    elif col_name == 'foreigners':
                        try:
                            summary_data['foreigners'] = int(cell_text.replace(',', ''))
                        except ValueError:
                            pass
                    elif col_name == 'avg_market_value':
                        amount, currency, _ = parse_money(cell_text)
                        if amount is not None:
                            summary_data['average_market_value'] = amount
                            summary_data['average_market_value_currency'] = currency
                    elif col_name == 'total_market_value':
                        amount, currency, _ = parse_money(cell_text)
                        if amount is not None:
                            summary_data['total_market_value'] = amount
                            summary_data['total_market_value_currency'] = currency
                
                if summary_data:
                    data['summary'] = summary_data
                    logger.debug("extracted_footer_summary", summary=summary_data)
    
    logger.info("bs_extraction_competition_clubs",
               competition_code=competition_code,
               clubs_count=len(data['clubs']),
               has_summary=bool(data['summary']))
    
    return data
