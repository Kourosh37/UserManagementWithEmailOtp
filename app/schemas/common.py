"""Shared lightweight schemas."""

from pydantic import BaseModel


class Message(BaseModel):
    """Standard response envelope used for plain text messages."""

    message: str
