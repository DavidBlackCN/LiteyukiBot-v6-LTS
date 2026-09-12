"""Persistent models for OneBot V11 friend requests."""

from pydantic import Field

from src.utils.base.data import LiteModel


class FriendRequest(LiteModel):
    TABLE_NAME: str = "liteyuki_friend_requests"

    request_id: int = Field(default=0)
    bot_id: str = Field(default="")
    user_id: str = Field(default="")
    comment: str = Field(default="")
    flag: str = Field(default="")
    created_at: str = Field(default="")
    status: str = Field(default="pending")
    handled_at: str = Field(default="")
    handled_by: str = Field(default="")


class FriendRequestSequence(LiteModel):
    """A separate counter keeps request IDs monotonic after history cleanup."""

    TABLE_NAME: str = "liteyuki_friend_request_sequence"

    next_request_id: int = Field(default=1)
