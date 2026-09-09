from pydantic import BaseModel, Field


class GitHubCardConfig(BaseModel):
    """Configuration for the local GitHub repository card plugin."""

    githubcard_token: str = ""
    githubcard_timeout: float = Field(default=8.0, ge=1.0, le=30.0)
