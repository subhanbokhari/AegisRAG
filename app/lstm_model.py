# app/lstm_model.py
"""Optimized LSTM model with quantization and caching support"""

import torch
import torch.nn as nn
from functools import lru_cache
import structlog

logger = structlog.get_logger()

class LSTMGuardrail(nn.Module):
    """
    Enhanced LSTM-based guardrail for security threat detection
    
    Features:
    - Efficient sequence processing with packed padding
    - Batch-ready architecture
    - Quantization-compatible design
    - Fast inference with fp16 support
    """
    
    def __init__(self, vocab_size: int = 1000, embedding_dim: int = 128, 
                 hidden_dim: int = 64, output_dim: int = 1, num_layers: int = 2,
                 dropout: float = 0.3):
        super(LSTMGuardrail, self).__init__()
        
        self.vocab_size = vocab_size
        self.embedding_dim = embedding_dim
        self.hidden_dim = hidden_dim
        self.output_dim = output_dim
        self.num_layers = num_layers
        
        # Embedding layer with padding
        self.embedding = nn.Embedding(vocab_size, embedding_dim, padding_idx=0)
        
        # Bidirectional LSTM for better context understanding
        self.lstm = nn.LSTM(
            embedding_dim, 
            hidden_dim, 
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
            bidirectional=True
        )
        
        # Attention-like mechanism: use both forward and backward hidden states
        self.fc_attention = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        
        # Classification head
        self.fc_classifier = nn.Sequential(
            nn.Linear(hidden_dim, 32),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(32, output_dim)
        )
        
        self.sigmoid = nn.Sigmoid()
        
        logger.info("LSTMGuardrail initialized", 
                   vocab_size=vocab_size,
                   embedding_dim=embedding_dim,
                   hidden_dim=hidden_dim,
                   num_layers=num_layers)
    
    def forward(self, text: torch.Tensor, text_lengths: torch.Tensor) -> torch.Tensor:
        """
        Forward pass with efficient sequence processing
        
        Args:
            text: Token tensor of shape (batch_size, seq_len)
            text_lengths: Actual lengths of sequences (batch_size,)
            
        Returns:
            Threat probability tensor of shape (batch_size, 1)
        """
        # Embedding: (batch_size, seq_len, embedding_dim)
        embedded = self.embedding(text)
        
        # Pack sequences to ignore padding during LSTM computation
        # This improves efficiency and prevents padding from affecting hidden states
        packed_embedded = nn.utils.rnn.pack_padded_sequence(
            embedded, 
            text_lengths.cpu(), 
            batch_first=True, 
            enforce_sorted=False
        )
        
        # LSTM forward pass
        # packed_output: contains all hidden states
        # (hidden, cell): final hidden and cell states
        packed_output, (hidden, cell) = self.lstm(packed_embedded)
        
        # Unpack sequences for further processing if needed
        output, output_lengths = nn.utils.rnn.pad_packed_sequence(packed_output, batch_first=True)
        
        # Use concatenated final hidden states from bidirectional LSTM
        # hidden shape: (num_layers * 2, batch_size, hidden_dim)
        # We use the last layer's hidden states
        final_hidden = hidden[-2:].transpose(0, 1).contiguous()  # (batch_size, 2, hidden_dim)
        final_hidden = final_hidden.view(final_hidden.size(0), -1)  # (batch_size, hidden_dim * 2)
        
        # Attention mechanism (simplified)
        attention_output = self.fc_attention(final_hidden)  # (batch_size, hidden_dim)
        
        # Classification
        logits = self.fc_classifier(attention_output)  # (batch_size, 1)
        
        # Sigmoid to get probability
        return self.sigmoid(logits)
    
    def quantize(self) -> 'LSTMGuardrail':
        """
        Prepare model for quantization (dynamic quantization)
        This reduces model size and improves inference speed
        """
        logger.info("Applying dynamic quantization to model")
        quantized = torch.quantization.quantize_dynamic(
            self,
            {torch.nn.LSTM, torch.nn.Linear},
            dtype=torch.qint8
        )
        return quantized
    
    def enable_amp(self):
        """Enable automatic mixed precision for faster inference"""
        logger.info("Enabling AMP (Automatic Mixed Precision)")
        self.half()  # Convert to fp16
        return self
    
    @staticmethod
    @lru_cache(maxsize=100)
    def create_default_model() -> 'LSTMGuardrail':
        """Factory method to create a cached instance of the default model"""
        logger.info("Creating default LSTMGuardrail model instance")
        return LSTMGuardrail(
            vocab_size=1000,
            embedding_dim=128,
            hidden_dim=64,
            num_layers=2,
            dropout=0.3
        )