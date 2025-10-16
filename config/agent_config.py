"""Agent configuration settings for HireMind application."""

from typing import Literal
from pydantic import BaseModel


class AgentConfig(BaseModel):
    """Configuration for the CV Extractor Agent."""
    
    model: str = "o1-pro"
    reasoning_effort: Literal["low", "medium", "high"] = "high"
    workflow_id: str = "wf_68e60e3448f88190876d9d86fda0b37b0897b64fb74e981c"
    store_conversations: bool = True
    max_retries: int = 3
    timeout_seconds: int = 300


# Default agent configuration
DEFAULT_AGENT_CONFIG = AgentConfig()
