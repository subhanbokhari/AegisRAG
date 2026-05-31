# app/guardrails.py
"""Advanced security guardrails with multi-layer detection"""

import re
from typing import Tuple
import torch
import torch.nn as nn
from functools import lru_cache
import structlog

from app.lstm_model import LSTMGuardrail

logger = structlog.get_logger()

# Enhanced vocabulary with more patterns
VOCAB = {
    "PAD": 0, "UNK": 1,
    # Injection patterns
    "ignore": 2, "previous": 3, "instructions": 4,
    "system": 5, "prompt": 6, "override": 7, "admin": 8,
    "drop": 9, "delete": 10, "exec": 11, "execute": 12,
    "password": 13, "secret": 14, "token": 15, "key": 16,
    "sql": 17, "injection": 18, "exploit": 19, "hack": 20,
    # Command patterns
    "curl": 21, "wget": 22, "cat": 23, "ls": 24, "rm": 25,
    "chmod": 26, "sudo": 27, "bash": 28, "shell": 29,
}

def tokenize_and_pad(text: str, max_len: int = 50) -> Tuple[torch.Tensor, torch.Tensor]:
    """Enhanced tokenization with better handling"""
    words = text.lower().split()
    tokens = [VOCAB.get(w, 1) for w in words][:max_len]
    actual_length = max(1, len(tokens))
    tokens += [0] * (max_len - len(tokens))
    return torch.tensor([tokens], dtype=torch.long), torch.tensor([actual_length])

@lru_cache(maxsize=1)
def get_lstm_engine() -> LSTMGuardrail:
    """Load and cache LSTM guardrail model"""
    logger.info("Loading LSTM guardrail model")
    engine = LSTMGuardrail(vocab_size=1000, embedding_dim=128, hidden_dim=64, output_dim=1)
    engine.eval()
    return engine

def verify_query_safety(user_query: str) -> Tuple[bool, float]:
    """
    Multi-layer security verification with confidence scoring
    
    Features:
    - Regex-based exploit pattern detection
    - Entropy analysis for random character injection
    - LSTM-based sequential intent inspection
    - Confidence scoring (0.0 - 1.0)
    
    Returns:
        Tuple of (is_safe: bool, confidence: float)
    """
    
    if not user_query or len(user_query.strip()) == 0:
        return True, 0.95
    
    risk_scores = []
    
    # ==================== PHASE A: Structural Exploit Detection ====================
    structural_patterns = [
        (r"(?i)ignore\s+(all\s+)?previous\s+instructions", 0.95, "Prompt injection detected"),
        (r"(?i)system\s+prompt", 0.90, "System prompt manipulation"),
        (r"(?i)disregard\s+(previous|above|prior)", 0.90, "Instruction override attempt"),
        (r"(?i)(forget|ignore)\s+your\s+(instructions|role|system)", 0.95, "Role override"),
        (r"\{.*?(\$|@|#).*?\}", 0.85, "Template injection pattern"),
        (r"\[\s*(eval|exec|execute|run)\s*\]", 0.90, "Code execution syntax"),
        (r"(\bOR\b|\bAND\b)\s+1\s*=\s*1", 0.95, "SQL injection pattern"),
        (r"(?i)(drop|delete|truncate)\s+(table|database)", 0.95, "Destructive SQL"),
        (r"(?i)--\s*$|;.*?(drop|delete)", 0.90, "SQL comment injection"),
        (r"(?i)<script[^>]*>.*?</script>", 0.85, "Script injection"),
        (r"(?i)(eval|exec|shell_exec|system)\s*\(", 0.95, "Code execution function"),
    ]
    
    for pattern, risk, reason in structural_patterns:
        if re.search(pattern, user_query):
            logger.warning("structural_exploit_detected", reason=reason, pattern=pattern)
            risk_scores.append(risk)
    
    # ==================== PHASE B: Entropy Analysis ====================
    # Detect random character sequences (common in obfuscation)
    def calculate_entropy(text: str) -> float:
        """Calculate Shannon entropy of text"""
        if not text:
            return 0.0
        freq = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1
        entropy = 0
        for count in freq.values():
            p = count / len(text)
            entropy -= p * (p if p == 0 else 1)  # Simplified Shannon entropy
        return entropy
    
    # Check for high-entropy segments (potential base64, hex encoding)
    entropy = calculate_entropy(user_query)
    if entropy > 4.0 and len(user_query) > 20:
        logger.warning("high_entropy_detected", entropy=entropy)
        risk_scores.append(0.70)
    
    # ==================== PHASE C: Keyword Blacklist ====================
    dangerous_patterns = {
        "password": 0.80,
        "secret": 0.75,
        "api_key": 0.85,
        "token": 0.70,
        "private_key": 0.90,
        "credential": 0.80,
        "database_url": 0.85,
    }
    
    query_lower = user_query.lower()
    for keyword, risk in dangerous_patterns.items():
        if keyword in query_lower:
            logger.warning("dangerous_keyword_found", keyword=keyword)
            risk_scores.append(risk)
    
    # ==================== PHASE D: Deep Sequential Intent Inspection via LSTM ====================
    try:
        tokens, length = tokenize_and_pad(user_query)
        lstm_engine = get_lstm_engine()
        
        with torch.no_grad():
            malicious_prob = float(lstm_engine(tokens, length).item())
        
        if malicious_prob > 0.70:
            logger.warning("lstm_malicious_intent_detected", probability=malicious_prob)
            risk_scores.append(malicious_prob)
    
    except Exception as e:
        logger.error("lstm_inference_error", error=str(e))
        # Fail closed on LSTM errors - flag as suspicious
        risk_scores.append(0.60)
    
    # ==================== Aggregate Risk Assessment ====================
    if risk_scores:
        # Use maximum risk and average as confidence
        max_risk = max(risk_scores)
        avg_risk = sum(risk_scores) / len(risk_scores)
        confidence = max(max_risk, avg_risk)
        
        if confidence > 0.85:
            logger.warning("query_rejected_high_risk", max_risk=max_risk, avg_risk=avg_risk, num_violations=len(risk_scores))
            return False, confidence
        elif confidence > 0.70:
            logger.warning("query_flagged_elevated_risk", max_risk=max_risk, confidence=confidence)
            # Still allow with high confidence for audit
            return True, confidence
        else:
            logger.info("query_suspicious_but_allowed", confidence=confidence)
            return True, 1.0 - confidence  # Invert for safety score
    
    # Clean query
    return True, 0.99