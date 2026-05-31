# app/main.py
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_client import Counter, Histogram, generate_latest
import structlog

from app.guardrails import verify_query_safety
from app.agents import agent_retrieve, agent_generate, agent_critic
from app.config import Settings

# Configuration
settings = Settings()

# Structured Logging Setup
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Metrics
query_counter = Counter('aegis_queries_total', 'Total queries processed', ['status'])
query_duration = Histogram('aegis_query_duration_seconds', 'Query processing duration')
security_violations = Counter('aegis_security_violations_total', 'Total security violations detected', ['type'])

# Rate Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

# Request/Response Models
class QueryPayload(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000, description="User query")
    request_timeout: Optional[int] = Field(30, ge=5, le=120, description="Request timeout in seconds")
    
    @validator('query')
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace")
        return v.strip()

class QueryResponse(BaseModel):
    status: str
    response: str
    request_id: str
    processing_time: float

class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: float

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    logger.info("AegisRAG application starting", version=settings.app_version)
    yield
    logger.info("AegisRAG application shutting down")

# Initialize FastAPI with enhanced security
app = FastAPI(
    title="AegisRAG Micro-Gateway",
    version=settings.app_version,
    description="Advanced RAG system with adversarial-resistant guardrails",
    lifespan=lifespan
)

# Security Middleware
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_credentials,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
    max_age=3600
)

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("Rate limit exceeded", path=request.url.path, client=get_remote_address(request))
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded. Maximum 100 requests per minute allowed."}
    )

@app.middleware("http")
async def add_request_context(request: Request, call_next):
    """Add request ID and timing context"""
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    request.state.request_id = request_id
    
    logger.info(
        "request_start",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client=get_remote_address(request)
    )
    
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = str(process_time)
    
    logger.info("request_end", request_id=request_id, status=response.status_code, duration=process_time)
    return response

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint for orchestration"""
    return HealthResponse(
        status="healthy",
        version=settings.app_version,
        timestamp=time.time()
    )

@app.get("/metrics", tags=["System"])
async def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest()

@app.post("/query", response_model=QueryResponse, tags=["RAG"], dependencies=[Depends(limiter.limit("100/minute"))])
async def execute_adversarial_rag(payload: QueryPayload, request: Request):
    """
    Execute query through adversarial-resistant RAG pipeline
    
    - **query**: User query (1-5000 characters)
    - **request_timeout**: Custom timeout (5-120 seconds, default 30)
    """
    request_id = request.state.request_id
    start_time = time.time()
    
    try:
        logger.info("query_received", request_id=request_id, query_length=len(payload.query))
        
        # 1. Firewall Interception Layer
        safety_check, confidence = verify_query_safety(payload.query)
        if not safety_check:
            security_violations.labels(type="injection_detected").inc()
            logger.warning(
                "security_violation",
                request_id=request_id,
                violation_type="injection_detected",
                confidence=confidence
            )
            raise HTTPException(
                status_code=403,
                detail=f"Security Violation: Exploit Attempt Blocked (confidence: {confidence:.2%})"
            )
        
        # 2. Sequential Agent Retrieval & Assembly
        context = await agent_retrieve(payload.query, timeout=payload.request_timeout)
        if not context:
            logger.warning("no_context_retrieved", request_id=request_id)
            context = ["No relevant context available in knowledge base."]
        
        answer = await agent_generate(payload.query, context)
        
        # 3. Post-Generation Integrity Evaluation
        audit_status, audit_score = agent_critic(context, answer)
        if audit_status == "REJECTED":
            security_violations.labels(type="integrity_violation").inc()
            logger.error(
                "integrity_violation",
                request_id=request_id,
                audit_score=audit_score
            )
            raise HTTPException(
                status_code=422,
                detail=f"Integrity Violation: Content Verification Fault (score: {audit_score:.2%})"
            )
        
        processing_time = time.time() - start_time
        query_duration.observe(processing_time)
        query_counter.labels(status="success").inc()
        
        logger.info(
            "query_success",
            request_id=request_id,
            audit_score=audit_score,
            processing_time=processing_time
        )
        
        return QueryResponse(
            status="SUCCESS",
            response=answer,
            request_id=request_id,
            processing_time=processing_time
        )
    
    except HTTPException:
        raise
    
    except Exception as e:
        query_counter.labels(status="error").inc()
        logger.exception(
            "query_error",
            request_id=request_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail="Internal server error during query processing")

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors"""
    request_id = getattr(request.state, 'request_id', 'unknown')
    logger.exception("unhandled_exception", request_id=request_id, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "request_id": request_id}
    )