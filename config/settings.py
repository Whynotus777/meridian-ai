"""Global configuration for Meridian AI.

Provider selection (auto-detected from environment):
    GOOGLE_API_KEY   set  →  Gemini Flash (free tier, recommended for testing)
    ANTHROPIC_API_KEY set →  Claude Sonnet (production)

Override manually:
    ModelConfig(provider="gemini",    model="gemini-2.5-flash")
    ModelConfig(provider="anthropic", model="claude-sonnet-4-20250514")
"""

import os
from dataclasses import dataclass, field
from typing import Optional

# Default models per provider
_PROVIDER_DEFAULTS = {
    "gemini":    "gemini-2.5-flash",
    "anthropic": "claude-sonnet-4-20250514",
}


def _detect_provider() -> str:
    """Auto-detect provider from available env vars. Gemini wins for free testing."""
    if os.environ.get("GOOGLE_API_KEY"):
        return "gemini"
    return "anthropic"


@dataclass
class ModelConfig:
    """LLM model configuration.

    Leave provider=None to auto-detect from environment variables.
    """
    provider: Optional[str] = None   # None → auto-detect
    model: Optional[str] = None      # None → default for provider
    max_tokens: int = 8192
    temperature: float = 0.0         # Deterministic for extraction
    api_key: Optional[str] = None

    def __post_init__(self):
        # Auto-detect provider
        if self.provider is None:
            self.provider = _detect_provider()

        # Set default model for provider
        if self.model is None:
            self.model = _PROVIDER_DEFAULTS.get(self.provider, "gemini-2.5-flash")

        # Resolve API key
        if self.api_key is None:
            if self.provider == "gemini":
                self.api_key = os.environ.get("GOOGLE_API_KEY")
            else:
                self.api_key = os.environ.get("ANTHROPIC_API_KEY")

        if not self.api_key:
            key_var = "GOOGLE_API_KEY" if self.provider == "gemini" else "ANTHROPIC_API_KEY"
            raise ValueError(
                f"{key_var} not set. Export it or pass api_key to ModelConfig.\n"
                f"  Gemini (free):    export GOOGLE_API_KEY=...   (get one at aistudio.google.com)\n"
                f"  Anthropic (paid): export ANTHROPIC_API_KEY=..."
            )


@dataclass
class ParserConfig:
    """Document parsing configuration."""
    max_pages: int = 150
    max_chars_per_page: int = 5000
    table_extraction: bool = True
    ocr_enabled: bool = False  # Phase 2: enable for scanned PDFs


@dataclass
class PipelineConfig:
    """Full pipeline configuration."""
    model: ModelConfig = field(default_factory=ModelConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    output_dir: str = "./output"
    verbose: bool = True

    # Feature flags for phased rollout
    enable_memo_generation: bool = True
    enable_comp_builder: bool = True
    enable_risk_analysis: bool = True
    enable_deal_scoring: bool = True
    enable_qa_engine: bool = True
    enable_fund_matching: bool = True

    # Phase 2+ flags (disabled in MVP)
    enable_data_room_ingestion: bool = False
    enable_contract_analysis: bool = False
    enable_portfolio_monitoring: bool = False
