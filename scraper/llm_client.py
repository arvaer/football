"""vLLM client wrapper for LLM-based extraction."""

import asyncio
import json
import time
import random
from typing import Optional, Dict, Any, List
from openai import AsyncOpenAI
import structlog

from scraper.config import settings

logger = structlog.get_logger()


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures."""
    
    def __init__(self, threshold: int, timeout: int):
        self.threshold = threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0
        self.is_open = False
        
    def record_success(self):
        """Record successful request."""
        self.failures = 0
        self.is_open = False
        
    def record_failure(self):
        """Record failed request."""
        self.failures += 1
        self.last_failure_time = time.time()
        
        if self.failures >= self.threshold:
            self.is_open = True
            logger.warning(
                "circuit_breaker_opened",
                failures=self.failures,
                threshold=self.threshold
            )
            
    def can_attempt(self) -> bool:
        """Check if request can be attempted."""
        if not self.is_open:
            return True
            
        # Check if timeout has elapsed
        if time.time() - self.last_failure_time > self.timeout:
            logger.info("circuit_breaker_half_open", timeout_elapsed=True)
            self.is_open = False
            self.failures = 0
            return True
            
        return False


class RateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, requests_per_minute: int, max_concurrent: int):
        self.requests_per_minute = requests_per_minute
        self.max_concurrent = max_concurrent
        self.tokens = requests_per_minute
        self.last_refill = time.time()
        self.active_requests = 0
        self.lock = asyncio.Lock()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
    async def acquire(self):
        """Acquire permission to make a request."""
        # First, wait for a concurrency slot
        await self.semaphore.acquire()
        
        async with self.lock:
            # Refill tokens based on time elapsed
            now = time.time()
            elapsed = now - self.last_refill
            tokens_to_add = elapsed * (self.requests_per_minute / 60.0)
            self.tokens = min(self.requests_per_minute, self.tokens + tokens_to_add)
            self.last_refill = now
            
            # Wait until we have a token
            while self.tokens < 1:
                wait_time = (1 - self.tokens) * (60.0 / self.requests_per_minute)
                logger.debug(
                    "rate_limit_waiting",
                    wait_time=wait_time,
                    tokens=self.tokens
                )
                await asyncio.sleep(wait_time)
                
                # Refill after waiting
                now = time.time()
                elapsed = now - self.last_refill
                tokens_to_add = elapsed * (self.requests_per_minute / 60.0)
                self.tokens = min(self.requests_per_minute, self.tokens + tokens_to_add)
                self.last_refill = now
                
            # Consume a token
            self.tokens -= 1
            self.active_requests += 1
            
    def release(self):
        """Release a request slot."""
        self.active_requests -= 1
        self.semaphore.release()


class LLMClient:
    """Async client for vLLM inference server with smart backoff and rate limiting."""
    
    def __init__(self):
        self.client = AsyncOpenAI(
            base_url=settings.vllm.base_url,
            api_key=settings.vllm.api_key,
        )
        self.model = settings.vllm.model_name
        
        # Initialize rate limiter and circuit breaker
        self.rate_limiter = RateLimiter(
            requests_per_minute=settings.vllm.requests_per_minute,
            max_concurrent=settings.vllm.max_concurrent_requests
        )
        self.circuit_breaker = CircuitBreaker(
            threshold=settings.vllm.circuit_breaker_threshold,
            timeout=settings.vllm.circuit_breaker_timeout
        )
        
    async def _execute_with_backoff(self, coro, operation_name: str):
        """Execute an async operation with exponential backoff and jitter."""
        if not self.circuit_breaker.can_attempt():
            raise Exception(
                f"Circuit breaker is open, refusing {operation_name}. "
                f"Server may be overloaded or down."
            )
        
        # Acquire rate limit token
        await self.rate_limiter.acquire()
        
        try:
            last_error = None
            for attempt in range(settings.vllm.max_retries):
                try:
                    result = await coro()
                    self.circuit_breaker.record_success()
                    return result
                    
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    
                    # Check if it's a retryable error
                    is_retryable = any([
                        "timeout" in error_str.lower(),
                        "rate limit" in error_str.lower(),
                        "too many requests" in error_str.lower(),
                        "503" in error_str,
                        "502" in error_str,
                        "504" in error_str,
                        "connection" in error_str.lower(),
                    ])
                    
                    if not is_retryable or attempt == settings.vllm.max_retries - 1:
                        # Non-retryable error or last attempt
                        self.circuit_breaker.record_failure()
                        raise
                    
                    # Calculate backoff with exponential increase and jitter
                    backoff = min(
                        settings.vllm.base_backoff_seconds * (2 ** attempt),
                        settings.vllm.max_backoff_seconds
                    )
                    # Add jitter: ±25% randomization
                    jitter = backoff * random.uniform(-0.25, 0.25)
                    sleep_time = backoff + jitter
                    
                    logger.warning(
                        "llm_request_retry",
                        operation=operation_name,
                        attempt=attempt + 1,
                        max_retries=settings.vllm.max_retries,
                        error=error_str,
                        backoff_seconds=sleep_time,
                    )
                    
                    await asyncio.sleep(sleep_time)
                    
            # If we exhausted all retries
            self.circuit_breaker.record_failure()
            raise last_error
            
        finally:
            self.rate_limiter.release()
        
    async def extract_structured_data(
        self,
        html_content: str,
        page_type: str,
        schema_description: str,
        few_shot_examples: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Extract structured data from HTML using LLM."""
        print(f"\nLLM CLIENT: extract_structured_data called for {page_type}")
        print(f"LLM CLIENT: HTML length: {len(html_content)}, schema length: {len(schema_description)}")
        start_time = time.time()
        
        # Build system prompt
        system_prompt = f"""You are a specialized web scraping assistant that extracts structured data from Transfermarkt HTML pages.

Page Type: {page_type}

Your task is to extract the following information and return it as valid JSON:
{schema_description}

Rules:
1. Return ONLY valid JSON, no markdown or explanation
2. Use null for missing values
3. Extract Transfermarkt IDs from URLs (e.g., "/player/123" -> "123")
4. Normalize dates to ISO format (YYYY-MM-DD)
5. For fees, extract numeric amount and currency separately
6. If information is not found, return empty structures rather than failing
"""

        print(f"LLM CLIENT: Built system prompt ({len(system_prompt)} chars)")

        # Add few-shot examples if provided
        messages = [{"role": "system", "content": system_prompt}]
        
        if few_shot_examples:
            for example in few_shot_examples:
                messages.append({
                    "role": "user",
                    "content": f"HTML:\n{example['html']}"
                })
                messages.append({
                    "role": "assistant",
                    "content": example['json']
                })
        
        # Add actual content
        # Qwen2.5-7B-Instruct has 32k context, use ~20k for HTML to leave room for prompt/output
        messages.append({
            "role": "user",
            "content": f"HTML:\n{html_content[:20000]}"  # Send more context
        })
        
        print(f"LLM CLIENT: Built {len(messages)} messages")
        print(f"LLM CLIENT: Sending request to {settings.vllm.base_url} with model {self.model}")
        print(f"LLM CLIENT: Message count: {len(messages)}, max_tokens: {settings.vllm.max_tokens}")
        
        async def _make_request():
            print(f"LLM CLIENT: Calling chat.completions.create...")
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=settings.vllm.temperature,
                max_tokens=settings.vllm.max_tokens,
            )
            print(f"LLM CLIENT: Got response!")
            print(f"LLM CLIENT: Response has {len(response.choices)} choices")
            return response
        
        try:
            response = await self._execute_with_backoff(
                _make_request,
                f"extract_{page_type}"
            )
            
            content = response.choices[0].message.content
            print(f"LLM CLIENT: Content length: {len(content)} chars")
            print(f"LLM CLIENT: Content preview: {content[:200]}...")
            
            # Try to extract JSON from response
            # Handle cases where LLM wraps in markdown code blocks
            if "```json" in content:
                print("LLM CLIENT: Unwrapping from ```json block")
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                print("LLM CLIENT: Unwrapping from ``` block")
                content = content.split("```")[1].split("```")[0].strip()
            
            print(f"LLM CLIENT: Parsing JSON...")
            result = json.loads(content)
            print(f"LLM CLIENT: JSON parsed successfully, keys: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            
            elapsed = (time.time() - start_time) * 1000
            logger.info(
                "llm_extraction_success",
                page_type=page_type,
                elapsed_ms=elapsed,
                tokens_used=response.usage.total_tokens if response.usage else 0,
            )
            
            return result
            
        except json.JSONDecodeError as e:
            print(f"LLM CLIENT: JSON DECODE ERROR: {e}")
            print(f"LLM CLIENT: Failed content: {content[:1000] if 'content' in locals() else 'N/A'}")
            logger.error(
                "llm_json_parse_error",
                page_type=page_type,
                error=str(e),
                content=content[:500] if 'content' in locals() else None,
            )
            raise
        except Exception as e:
            print(f"LLM CLIENT: EXCEPTION: {type(e).__name__}: {e}")
            import traceback
            print(f"LLM CLIENT: Traceback:\n{traceback.format_exc()}")
            logger.error(
                "llm_extraction_error",
                page_type=page_type,
                error=str(e),
                exc_info=True,
            )
            raise
            
    async def repair_selectors(
        self,
        html_snippet: str,
        failed_selectors: Dict[str, str],
        fields_to_extract: List[str],
    ) -> Dict[str, str]:
        """Generate new CSS selectors for failed extractions."""
        start_time = time.time()
        
        system_prompt = """You are a CSS selector expert. Given HTML and failed selectors, suggest new ones.

Return ONLY valid JSON in this format:
{
  "field_name": "css_selector",
  ...
}

Rules:
1. Return ONLY the JSON object, no explanation
2. Suggest specific, robust selectors
3. Prefer class and data attributes over complex nesting
4. Test mentally that selector would work on the HTML
"""

        failed_info = "\n".join([f"- {field}: '{selector}' (FAILED)" 
                                  for field, selector in failed_selectors.items()])
        
        user_prompt = f"""Previously failed selectors:
{failed_info}

Fields to extract: {', '.join(fields_to_extract)}

HTML:
{html_snippet[:4000]}

Suggest new CSS selectors for: {', '.join(fields_to_extract)}
"""

        async def _make_request():
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,  # Lower temperature for more deterministic output
                max_tokens=256,  # Reduced to fit within context limits
            )
            return response
        
        try:
            response = await self._execute_with_backoff(
                _make_request,
                "repair_selectors"
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
                
            result = json.loads(content)
            
            elapsed = (time.time() - start_time) * 1000
            logger.info(
                "selector_repair_success",
                elapsed_ms=elapsed,
                new_selectors=list(result.keys()),
            )
            
            return result
            
        except Exception as e:
            logger.error(
                "selector_repair_error",
                error=str(e),
                exc_info=True,
            )
            raise


# Global LLM client instance
_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create the global LLM client."""
    global _llm_client
    
    if _llm_client is None:
        _llm_client = LLMClient()
        
    return _llm_client
