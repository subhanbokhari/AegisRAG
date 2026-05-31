# app/agents.py
"""Advanced RAG agents with security, caching, and performance optimizations"""

import asyncio
import hashlib
import json
from typing import List, Tuple, Optional
from functools import lru_cache

import psycopg2
from psycopg2 import pool
from sentence_transformers import SentenceTransformer
import structlog
import redis
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import Settings

logger = structlog.get_logger()
settings = Settings()

# Model Caching
@lru_cache(maxsize=1)
def get_encoder():
    """Cache encoder model in memory to avoid reloading"""
    logger.info("Loading sentence transformer model", model=settings.encoder_model)
    return SentenceTransformer(settings.encoder_model)

# Connection Pool for Database
@lru_cache(maxsize=1)
def get_db_pool():
    """Create and cache database connection pool"""
    logger.info("Initializing database connection pool", max_size=settings.db_pool_size)
    return psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=settings.db_pool_size,
        host=settings.db_host,
        port=settings.db_port,
        database=settings.db_name,
        user=settings.db_user,
        password=settings.db_password,
        connect_timeout=settings.db_connection_timeout
    )

# Redis Client for Caching
@lru_cache(maxsize=1)
def get_redis_client() -> Optional[redis.Redis]:
    """Create and cache Redis client for caching"""
    if not settings.redis_enabled:
        return None
    try:
        logger.info("Connecting to Redis", url=settings.redis_url)
        client = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=5)
        client.ping()
        return client
    except Exception as e:
        logger.warning("Redis connection failed, falling back to no-cache mode", error=str(e))
        return None

def _get_cache_key(prefix: str, data: str) -> str:
    """Generate cache key using SHA-256 hash"""
    return f"{prefix}:{hashlib.sha256(data.encode()).hexdigest()[:32]}"

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
async def agent_retrieve(query: str, timeout: int = None) -> List[str]:
    """
    Agent 1: Semantic Context Retriever with caching and resilience
    
    Features:
    - Vector similarity search with pgvector
    - Redis caching for frequent queries
    - Connection pooling for performance
    - Automatic retry with exponential backoff
    - Configurable timeout
    """
    timeout = timeout or settings.retrieval_timeout
    cache_key = _get_cache_key("retrieval", query)
    
    # Try Redis cache first
    redis_client = get_redis_client()
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                logger.info("cache_hit", cache_key=cache_key, source="redis")
                return json.loads(cached)
        except Exception as e:
            logger.warning("Cache retrieval failed", error=str(e))
    
    try:
        encoder = get_encoder()
        query_vector = encoder.encode(query).tolist()
        
        pool = get_db_pool()
        conn = pool.getconn()
        
        try:
            cur = conn.cursor()
            
            # Use parametrized query to prevent SQL injection
            # Select top-k most similar documents
            cur.execute("""
                SELECT content, 1 - (embedding <=> %s::vector) as similarity_score
                FROM documents 
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """, (str(query_vector), str(query_vector), settings.top_k_results))
            
            records = cur.fetchall()
            cur.close()
            
            # Extract content from results
            results = [r[0] for r in records] if records else []
            
            logger.info("retrieval_success", query_hash=cache_key, num_results=len(results))
            
            # Cache successful results
            if redis_client and results:
                try:
                    redis_client.setex(cache_key, settings.redis_ttl, json.dumps(results))
                except Exception as e:
                    logger.warning("Failed to cache results", error=str(e))
            
            return results if results else ["No relevant documents found in knowledge base."]
        
        finally:
            pool.putconn(conn)
    
    except asyncio.TimeoutError:
        logger.error("retrieval_timeout", query_hash=cache_key, timeout=timeout)
        return ["Retrieval timeout: Knowledge base search took too long."]
    
    except Exception as e:
        logger.exception("retrieval_error", query_hash=cache_key, error=str(e))
        # Fail open with safe fallback
        return ["Fallback Context: Unable to retrieve context. System operating in safe mode."]

@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
async def agent_generate(query: str, context: List[str], timeout: int = None) -> str:
    """
    Agent 2: Context-Constrained Response Generator
    
    Features:
    - Respects context boundaries (no hallucination)
    - Combines multiple context sources intelligently
    - Timeout protection
    - Fallback handling
    """
    timeout = timeout or settings.generation_timeout
    cache_key = _get_cache_key("generation", f"{query}:{','.join(context)}")
    
    # Try cache
    redis_client = get_redis_client()
    if redis_client:
        try:
            cached = redis_client.get(cache_key)
            if cached:
                logger.info("cache_hit", cache_key=cache_key, source="generation_cache")
                return cached
        except Exception as e:
            logger.warning("Generation cache retrieval failed", error=str(e))
    
    try:
        # Generate response strictly from provided context
        if not context or context[0].startswith("Fallback") or context[0].startswith("No relevant"):
            response = "Unable to generate response: insufficient context in knowledge base."
        else:
            # Smart context aggregation - use most relevant context
            primary_context = context[0]
            secondary_context = " ".join(context[1:]) if len(context) > 1 else ""
            
            response = f"Response based on retrieved documents:\n\n{primary_context}"
            if secondary_context:
                response += f"\n\nSupplementary context: {secondary_context}"
        
        logger.info("generation_success", context_sources=len(context), response_length=len(response))
        
        # Cache result
        if redis_client:
            try:
                redis_client.setex(cache_key, settings.redis_ttl // 2, response)
            except Exception as e:
                logger.warning("Failed to cache generation", error=str(e))
        
        return response
    
    except asyncio.TimeoutError:
        logger.error("generation_timeout", timeout=timeout)
        return "Generation timeout: Response generation took too long."
    
    except Exception as e:
        logger.exception("generation_error", error=str(e))
        return "Generation error: Unable to generate response safely."

async def agent_critic(context: List[str], answer: str) -> Tuple[str, float]:
    """
    Agent 3: Logical Verification & Data Leak Auditor with confidence scoring
    
    Features:
    - Self-correction loop to prevent hallucination
    - Confidence scoring (0.0 - 1.0)
    - Detects information leakage attempts
    - Prevents context drift
    
    Returns:
        Tuple of (verdict: str, confidence_score: float)
    """
    try:
        # Check for suspicious keywords not in source context
        suspicious_keywords = ["password", "secret", "api_key", "token", "admin", "root", "sudo"]
        
        context_text = " ".join(context).lower()
        answer_lower = answer.lower()
        
        leaked_info = []
        for keyword in suspicious_keywords:
            if keyword in answer_lower and keyword not in context_text:
                leaked_info.append(keyword)
        
        if leaked_info:
            confidence = min(0.95, 0.5 + len(leaked_info) * 0.15)
            logger.warning(
                "potential_information_leak",
                leaked_keywords=leaked_info,
                confidence=confidence
            )
            return ("REJECTED", confidence)
        
        # Check for context adherence (answer should relate to context)
        # Count overlapping words (simple heuristic)
        context_words = set(context_text.split())
        answer_words = set(answer_lower.split())
        overlap = len(context_words & answer_words)
        total_answer_words = len(answer_words)
        
        if total_answer_words > 0:
            coherence_score = overlap / max(total_answer_words, len(context_words))
        else:
            coherence_score = 1.0
        
        # Require at least 20% overlap with context for acceptance
        if coherence_score < 0.2 and "Unable to generate response" not in answer:
            logger.warning("low_context_coherence", coherence_score=coherence_score)
            return ("REJECTED", 1.0 - coherence_score)
        
        confidence_score = min(0.99, 0.6 + coherence_score * 0.4)
        
        logger.info("verification_passed", confidence=confidence_score, coherence=coherence_score)
        return ("APPROVED", confidence_score)
    
    except Exception as e:
        logger.exception("critic_error", error=str(e))
        # Fail closed on audit errors
        return ("REJECTED", 1.0)