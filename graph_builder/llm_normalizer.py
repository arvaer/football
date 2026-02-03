"""
LLM-based intelligent normalization for club names.

Uses vLLM to detect semantic equivalence between club name variants
(e.g., "AC La Havre" vs "Le Havre AC") and normalize to canonical forms.
"""

import asyncio
import json
from typing import Dict, Optional, Set, List
from openai import AsyncOpenAI
import structlog

logger = structlog.get_logger()


class ClubNameNormalizer:
    """
    Intelligent club name normalizer using LLM.
    
    Maintains a cache of normalized names to avoid redundant LLM calls.
    """
    
    def __init__(
        self,
        base_url: str = "http://localhost:8000/v1",
        api_key: str = "token",
        model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    ):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        
        # Cache: variant -> canonical name
        self.normalization_cache: Dict[str, str] = {}
        
        # Track clusters of equivalent names
        self.equivalence_clusters: List[Set[str]] = []
        
    async def normalize_batch(self, club_names: List[str]) -> Dict[str, str]:
        """
        Normalize a batch of club names to their canonical forms.
        
        Args:
            club_names: List of club names to normalize
            
        Returns:
            Dict mapping each input name to its canonical form
        """
        # Filter out already-cached names
        uncached = [name for name in club_names if name not in self.normalization_cache]
        
        if not uncached:
            return {name: self.normalization_cache[name] for name in club_names}
        
        # Build prompt for LLM
        prompt = self._build_normalization_prompt(uncached)
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a football/soccer domain expert specializing in club name normalization. "
                            "Your task is to identify semantic equivalents among club names and standardize them to canonical forms. "
                            "Consider variations in: article placement (AC/AS/FC prefix vs suffix), abbreviations, "
                            "spelling variations, full vs short names, and common aliases."
                        )
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.1,
                max_tokens=2048,
                response_format={"type": "json_object"}
            )
            
            # Parse response
            result = json.loads(response.choices[0].message.content)
            normalizations = result.get("normalizations", {})
            
            # Update cache
            self.normalization_cache.update(normalizations)
            
            # Update equivalence clusters
            self._update_clusters(normalizations)
            
            # Return full mapping (cached + new)
            return {name: self.normalization_cache.get(name, name) for name in club_names}
            
        except Exception as e:
            logger.error("llm_normalization_failed", error=str(e))
            # Fallback: return names as-is
            return {name: name for name in club_names}
    
    def _build_normalization_prompt(self, club_names: List[str]) -> str:
        """Build a prompt for club name normalization."""
        names_str = "\n".join([f"- {name}" for name in club_names])
        
        return f"""Analyze the following football club names and identify groups that refer to the same club.
For each group, select the most canonical/official name as the normalized form.

Club names to analyze:
{names_str}

Rules:
1. "AC Milano" and "AC Milan" are the same club → normalize to "AC Milan"
2. "Le Havre AC" and "AC Le Havre" are the same club → normalize to "Le Havre AC" (official form)
3. "Paris Saint-Germain" and "PSG" are the same club → normalize to "Paris Saint-Germain" (full official name)
4. "Manchester United" and "Man United" are the same club → normalize to "Manchester United"
5. Preserve the official spelling and article placement
6. Keep different clubs separate (e.g., "Manchester United" ≠ "Manchester City")
7. If a club has multiple valid names in the list, pick the most complete/official one

Return a JSON object with this structure:
{{
  "normalizations": {{
    "input_name_1": "canonical_name_1",
    "input_name_2": "canonical_name_1",  // if same club as #1
    "input_name_3": "canonical_name_3",  // if different club
    ...
  }},
  "reasoning": {{
    "canonical_name_1": "Reason for choosing this as canonical form",
    ...
  }}
}}

For each input name, map it to its canonical form. If a name is already canonical, map it to itself.
"""
    
    def _update_clusters(self, normalizations: Dict[str, str]):
        """Update equivalence clusters based on new normalizations."""
        # Group names by their canonical form
        canonical_groups: Dict[str, Set[str]] = {}
        for variant, canonical in normalizations.items():
            if canonical not in canonical_groups:
                canonical_groups[canonical] = set()
            canonical_groups[canonical].add(variant)
            canonical_groups[canonical].add(canonical)
        
        # Merge with existing clusters
        for canonical, variants in canonical_groups.items():
            # Find if any existing cluster contains these variants
            merged = False
            for cluster in self.equivalence_clusters:
                if cluster & variants:  # If there's overlap
                    cluster.update(variants)
                    merged = True
                    break
            
            if not merged:
                self.equivalence_clusters.append(variants)
    
    def get_canonical(self, club_name: str) -> str:
        """
        Get canonical name for a club (synchronous wrapper).
        
        If not in cache, returns the original name.
        """
        return self.normalization_cache.get(club_name, club_name)
    
    def export_cache(self) -> Dict[str, str]:
        """Export normalization cache for persistence."""
        return self.normalization_cache.copy()
    
    def import_cache(self, cache: Dict[str, str]):
        """Import normalization cache from persistence."""
        self.normalization_cache.update(cache)
        # Rebuild clusters
        self._update_clusters(cache)


async def normalize_club_names_from_data(data_dir: str = "data/extracted") -> Dict[str, str]:
    """
    Scan JSONL data files and build a normalization mapping.
    
    This is a one-time operation to build the normalization cache.
    
    Args:
        data_dir: Directory containing JSONL files
        
    Returns:
        Dict mapping variant names to canonical names
    """
    from pathlib import Path
    
    # Collect all unique club names from data
    club_names: Set[str] = set()
    
    data_path = Path(data_dir)
    
    # Load from club_transfers
    for jsonl_file in data_path.glob("club_transfers_*.jsonl"):
        with open(jsonl_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if not record.get('success'):
                        continue
                    
                    for transfer in record.get('transfers', []):
                        from_club = transfer.get('from_club')
                        to_club = transfer.get('to_club')
                        
                        if from_club and isinstance(from_club, str):
                            club_names.add(from_club.strip())
                        if to_club and isinstance(to_club, str):
                            club_names.add(to_club.strip())
                            
                except (json.JSONDecodeError, KeyError):
                    continue
    
    # Load from player_profile (current_club)
    for jsonl_file in data_path.glob("player_profile_*.jsonl"):
        with open(jsonl_file, 'r') as f:
            for line in f:
                try:
                    record = json.loads(line)
                    if not record.get('success'):
                        continue
                    
                    data = record.get('data', {})
                    current_club = data.get('current_club')
                    
                    if current_club and isinstance(current_club, str):
                        club_names.add(current_club.strip())
                        
                except (json.JSONDecodeError, KeyError):
                    continue
    
    # Filter out invalid names
    club_names = {
        name for name in club_names
        if name and len(name) > 1 and name.lower() not in ['unknown', 'none', 'n/a', '-']
    }
    
    logger.info("collected_club_names", count=len(club_names))
    
    # Initialize normalizer
    normalizer = ClubNameNormalizer()
    
    # Normalize in batches (LLM context window limit)
    batch_size = 100
    club_list = sorted(club_names)
    
    for i in range(0, len(club_list), batch_size):
        batch = club_list[i:i + batch_size]
        logger.info("normalizing_batch", batch_num=i // batch_size + 1, size=len(batch))
        await normalizer.normalize_batch(batch)
    
    logger.info("normalization_complete", 
                unique_clubs=len(set(normalizer.normalization_cache.values())),
                total_variants=len(normalizer.normalization_cache))
    
    return normalizer.export_cache()


# Singleton instance for reuse
_normalizer_instance: Optional[ClubNameNormalizer] = None


def get_normalizer() -> ClubNameNormalizer:
    """Get or create the singleton normalizer instance."""
    global _normalizer_instance
    if _normalizer_instance is None:
        _normalizer_instance = ClubNameNormalizer()
    return _normalizer_instance
