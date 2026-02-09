"""Pydantic models for scraping tasks and extracted data."""

from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, HttpUrl, field_validator


class PageType(str, Enum):
    """Types of Transfermarkt pages."""
    
    LEAGUE_INDEX = "league_index"
    LEAGUE_INDEX_BS = "league_index_bs"  # BeautifulSoup deterministic extraction
    LEAGUE_INDEX_ENRICH = "league_index_enrich"  # LLM enrichment/validation
    LEAGUE_CLUBS = "league_clubs"
    CLUB_PROFILE = "club_profile"
    CLUB_TRANSFERS = "club_transfers"
    PLAYER_PROFILE = "player_profile"
    PLAYER_TRANSFERS = "player_transfers"
    COMPETITION_PAGE = "competition_page"
    UNKNOWN = "unknown"


class TaskPriority(int, Enum):
    """Task priority levels."""
    
    LOW = 2
    MEDIUM = 5
    HIGH = 8
    CRITICAL = 10


class ScrapingTask(BaseModel):
    """Task to be queued for scraping."""
    
    url: str
    page_type: PageType
    priority: int = Field(default=TaskPriority.MEDIUM, ge=0, le=10)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    retry_count: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class Currency(str, Enum):
    """Currency codes."""
    
    EUR = "EUR"
    GBP = "GBP"
    USD = "USD"
    UNKNOWN = "UNKNOWN"


class TransferType(str, Enum):
    """Type of transfer."""
    
    PERMANENT = "permanent"
    LOAN = "loan"
    FREE = "free"
    END_OF_LOAN = "end_of_loan"
    UNKNOWN = "unknown"


class Position(str, Enum):
    """Normalized player positions."""
    
    GK = "GK"  # Goalkeeper
    CB = "CB"  # Center Back
    LB = "LB"  # Left Back
    RB = "RB"  # Right Back
    DM = "DM"  # Defensive Midfielder
    CM = "CM"  # Central Midfielder
    AM = "AM"  # Attacking Midfielder
    LW = "LW"  # Left Winger
    RW = "RW"  # Right Winger
    CF = "CF"  # Center Forward
    ST = "ST"  # Striker
    UNKNOWN = "UNKNOWN"


class Fee(BaseModel):
    """Transfer fee details."""
    
    amount: Optional[float] = None
    currency: Currency = Field(default=Currency.EUR)  # Default to EUR
    is_disclosed: bool = Field(default=True)  # Default to true
    has_addons: bool = False
    is_loan_fee: bool = False
    notes: Optional[str] = None
    
    class Config:
        use_enum_values = True


class Player(BaseModel):
    """Player entity."""
    
    tm_id: Optional[str] = None  # Transfermarkt ID from URL
    name: Optional[str] = None
    date_of_birth: Optional[datetime] = None
    nationality: Optional[str] = None
    height_cm: Optional[int] = None
    position: Position = Position.UNKNOWN
    dominant_foot: Optional[str] = None
    current_club: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class Club(BaseModel):
    """Club entity."""
    
    tm_id: Optional[str] = None  # Transfermarkt ID from URL
    name: Optional[str] = None
    country: Optional[str] = None
    league: Optional[str] = None
    division: Optional[int] = None
    squad_size: Optional[int] = None  # Number of players in squad
    average_age: Optional[float] = None  # Average age of squad
    foreigners: Optional[int] = None  # Number of foreign players
    average_market_value: Optional[float] = None  # Avg market value per player (millions EUR)
    total_market_value: Optional[float] = None  # Total squad market value (millions EUR)
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class Transfer(BaseModel):
    """Transfer record."""
    
    player_tm_id: Optional[str] = None
    player_name: Optional[str] = None
    from_club: Optional[str] = None
    from_club_tm_id: Optional[str] = None
    to_club: Optional[str] = None
    to_club_tm_id: Optional[str] = None
    transfer_date: Optional[datetime] = None
    season: Optional[str] = None
    transfer_type: TransferType = TransferType.UNKNOWN
    fee: Optional[Fee] = None
    market_value_at_transfer: Optional[float] = None
    contract_length: Optional[str] = None
    source_url: str
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class MarketValue(BaseModel):
    """Market value snapshot."""
    
    player_tm_id: str
    value: float
    currency: Currency = Currency.EUR
    date: datetime
    club: Optional[str] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class ExtractionResult(BaseModel):
    """Result from LLM extraction."""
    
    success: bool
    page_type: PageType
    url: str
    data: Dict[str, Any] = Field(default_factory=dict)
    players: List[Player] = Field(default_factory=list)
    clubs: List[Club] = Field(default_factory=list)
    transfers: List[Transfer] = Field(default_factory=list)
    market_values: List[MarketValue] = Field(default_factory=list)
    error: Optional[str] = None
    extraction_time_ms: Optional[float] = None
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    
    # Extraction backend tracking
    extraction_backend: str = Field(default="llm")  # "llm", "bs", or "bs_fallback_llm"
    
    # Validation tracking
    validation: Optional[Dict[str, Any]] = Field(default=None)
    
    class Config:
        use_enum_values = True


class ValidationReport(BaseModel):
    """LLM validation report for deterministic extraction."""
    
    warnings: List[str] = Field(default_factory=list)
    suggested_fixes: List[Dict[str, Any]] = Field(default_factory=list)
    fixes_applied: List[str] = Field(default_factory=list)
    needs_review: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    validation_notes: Optional[str] = None
    validated_at: datetime = Field(default_factory=datetime.utcnow)


class CompetitionClubStats(BaseModel):
    """Club statistics within a competition."""
    
    tm_id: Optional[str] = None
    name: str
    squad_size: Optional[int] = None
    average_age: Optional[float] = None
    foreigners: Optional[int] = None
    average_market_value: Optional[float] = None  # millions
    average_market_value_currency: Optional[str] = None
    total_market_value: Optional[float] = None  # millions
    total_market_value_currency: Optional[str] = None


class CompetitionClubs(BaseModel):
    """Competition clubs data with statistics."""
    
    competition_code: Optional[str] = None
    competition_name: Optional[str] = None
    url: str
    clubs: List[CompetitionClubStats] = Field(default_factory=list)
    summary: Optional[CompetitionClubStats] = None
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class RepairTask(BaseModel):
    """Task for selector repair agent."""
    
    url: str
    page_type: PageType
    html_snippet: str
    failed_selectors: Dict[str, str]
    error_message: str
    original_task: ScrapingTask
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SelectorSuggestion(BaseModel):
    """LLM-generated selector suggestions."""
    
    field_name: str
    css_selector: Optional[str] = None
    xpath: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: Optional[str] = None

