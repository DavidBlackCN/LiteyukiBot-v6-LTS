"""Configuration for the built-in friend request manager."""

from pydantic import BaseModel, Field


class FriendRequestConfig(BaseModel):
    friend_request_enabled: bool = True
    friend_request_history_days: int = Field(default=30, ge=0, le=3650)
