"""LLM-based validator for deterministic extraction results.

This validator:
- Detects anomalies in extracted data
- Suggests corrections for edge cases
- Enriches data (e.g., position normalization)
- Does NOT prevent extraction results from being persisted
"""

import asyncio
from typing import Dict, Any, List, Optional
import structlog

from scraper.models import ValidationReport, PageType
from scraper.llm_client import get_llm_client

logger = structlog.get_logger()


class TransfermarktValidator:
    """LLM-based validator for Transfermarkt extraction."""
    
    def __init__(self):
        self.llm = get_llm_client()
    
    async def validate_player_profile(
        self,
        extracted_data: Dict[str, Any],
        html_snippet: Optional[str] = None
    ) -> ValidationReport:
        """
        Validate player profile extraction.
        
        Args:
            extracted_data: Dict from BS extraction
            html_snippet: Optional small HTML snippet for context
        
        Returns:
            ValidationReport with warnings and suggested fixes
        """
        report = ValidationReport()
        
        player = extracted_data.get("player", {})
        
        # Check for missing critical fields
        if not player.get("tm_id"):
            report.warnings.append("Missing player tm_id")
            report.needs_review = True
        
        if not player.get("name"):
            report.warnings.append("Missing player name")
            report.needs_review = True
        
        # Check position normalization
        position = player.get("position")
        if position and position == "UNKNOWN":
            report.warnings.append(f"Position could not be normalized: {position}")
            report.needs_review = True
        
        # Check for suspicious height values
        height = player.get("height_cm")
        if height:
            if height < 150 or height > 220:
                report.warnings.append(f"Suspicious height value: {height}cm")
                report.needs_review = True
        
        # Check date format
        dob = player.get("date_of_birth")
        if dob and not isinstance(dob, str):
            report.warnings.append(f"Invalid date format for date_of_birth: {dob}")
        
        logger.info("validated_player_profile", 
                   warnings=len(report.warnings),
                   needs_review=report.needs_review)
        
        return report
    
    async def validate_player_transfers(
        self,
        extracted_data: Dict[str, Any],
        html_snippet: Optional[str] = None
    ) -> ValidationReport:
        """
        Validate player transfers extraction.
        
        Args:
            extracted_data: Dict from BS extraction
            html_snippet: Optional small HTML snippet for context
        
        Returns:
            ValidationReport with warnings and suggested fixes
        """
        report = ValidationReport()
        
        transfers = extracted_data.get("transfers", [])
        
        if not transfers:
            report.warnings.append("No transfers found")
            report.confidence = 0.5
        
        for i, transfer in enumerate(transfers):
            # Check for missing clubs
            if not transfer.get("from_club") and not transfer.get("to_club"):
                report.warnings.append(f"Transfer {i}: Missing both from_club and to_club")
                report.needs_review = True
            
            # Check fee parsing
            fee = transfer.get("fee", {})
            if fee:
                amount = fee.get("amount")
                
                # Suspicious: very large amounts (might be parsing error)
                if amount and amount > 500:
                    report.warnings.append(
                        f"Transfer {i}: Suspicious fee amount {amount}m "
                        f"(might be parsing error)"
                    )
                    report.needs_review = True
                
                # Check currency consistency
                currency = fee.get("currency")
                if currency and currency not in ["EUR", "GBP", "USD"]:
                    report.warnings.append(f"Transfer {i}: Invalid currency {currency}")
        
        logger.info("validated_player_transfers",
                   transfers=len(transfers),
                   warnings=len(report.warnings),
                   needs_review=report.needs_review)
        
        return report
    
    async def validate_club_transfers(
        self,
        extracted_data: Dict[str, Any],
        html_snippet: Optional[str] = None
    ) -> ValidationReport:
        """
        Validate club transfers extraction.
        
        Args:
            extracted_data: Dict from BS extraction
            html_snippet: Optional small HTML snippet for context
        
        Returns:
            ValidationReport with warnings and suggested fixes
        """
        report = ValidationReport()
        
        club_id = extracted_data.get("club_tm_id")
        club_name = extracted_data.get("club_name")
        transfers = extracted_data.get("transfers", [])
        
        if not club_id:
            report.warnings.append("Missing club_tm_id")
            report.needs_review = True
        
        if not club_name:
            report.warnings.append("Missing club_name")
        
        if not transfers:
            report.warnings.append("No transfers found")
            report.confidence = 0.5
        
        for i, transfer in enumerate(transfers):
            # Check for missing player
            if not transfer.get("player_name") and not transfer.get("player_tm_id"):
                report.warnings.append(f"Transfer {i}: Missing player information")
                report.needs_review = True
            
            # Check fee parsing
            fee = transfer.get("fee", {})
            if fee:
                amount = fee.get("amount")
                
                # Suspicious amounts
                if amount and amount > 500:
                    report.warnings.append(
                        f"Transfer {i}: Suspicious fee amount {amount}m "
                        f"(player: {transfer.get('player_name', 'unknown')})"
                    )
                    report.needs_review = True
                
                # Check for proper unit parsing
                notes = fee.get("notes", "")
                if notes and ("€" in notes or "£" in notes or "$" in notes):
                    # Fee has currency symbol in notes - might need re-parsing
                    if amount is None:
                        report.warnings.append(
                            f"Transfer {i}: Fee notes contain currency but amount is None: {notes}"
                        )
        
        logger.info("validated_club_transfers",
                   club_id=club_id,
                   transfers=len(transfers),
                   warnings=len(report.warnings),
                   needs_review=report.needs_review)
        
        return report
    
    async def validate_club_profile(
        self,
        extracted_data: Dict[str, Any],
        html_snippet: Optional[str] = None
    ) -> ValidationReport:
        """
        Validate club profile extraction.
        
        Args:
            extracted_data: Dict from BS extraction
            html_snippet: Optional small HTML snippet for context
        
        Returns:
            ValidationReport with warnings and suggested fixes
        """
        report = ValidationReport()
        
        club = extracted_data.get("club", {})
        
        if not club.get("tm_id"):
            report.warnings.append("Missing club tm_id")
            report.needs_review = True
        
        if not club.get("name"):
            report.warnings.append("Missing club name")
            report.needs_review = True
        
        # Check division is reasonable
        division = club.get("division")
        if division:
            if division < 1 or division > 10:
                report.warnings.append(f"Suspicious division value: {division}")
                report.needs_review = True
        
        logger.info("validated_club_profile",
                   warnings=len(report.warnings),
                   needs_review=report.needs_review)
        
        return report
    
    async def validate(
        self,
        extracted_data: Dict[str, Any],
        page_type: PageType,
        html_snippet: Optional[str] = None
    ) -> ValidationReport:
        """
        Validate extraction based on page type.
        
        Args:
            extracted_data: Dict from BS extraction
            page_type: Type of page
            html_snippet: Optional small HTML snippet for context
        
        Returns:
            ValidationReport
        """
        try:
            if page_type == PageType.PLAYER_PROFILE:
                return await self.validate_player_profile(extracted_data, html_snippet)
            elif page_type == PageType.PLAYER_TRANSFERS:
                return await self.validate_player_transfers(extracted_data, html_snippet)
            elif page_type == PageType.CLUB_TRANSFERS:
                return await self.validate_club_transfers(extracted_data, html_snippet)
            elif page_type == PageType.CLUB_PROFILE:
                return await self.validate_club_profile(extracted_data, html_snippet)
            else:
                # Unsupported page type
                report = ValidationReport()
                report.warnings.append(f"Validation not implemented for {page_type}")
                return report
        
        except Exception as e:
            logger.error("validation_error", page_type=page_type, error=str(e))
            report = ValidationReport()
            report.warnings.append(f"Validation error: {str(e)}")
            report.needs_review = True
            return report


# Global validator instance
_validator = None


def get_validator() -> TransfermarktValidator:
    """Get global validator instance."""
    global _validator
    if _validator is None:
        _validator = TransfermarktValidator()
    return _validator
