from pydantic import BaseModel, Field
from typing import Optional

class MailingData(BaseModel):
    message_id: int
    from_chat_id: int
    reply_markup: Optional[dict] = Field(default=None)
    is_vip: bool
    is_premium: bool
    is_chats: bool
    is_pin: bool