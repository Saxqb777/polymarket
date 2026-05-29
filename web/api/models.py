"""Pydantic schemas for request/response validation."""
from typing import Optional, List
from pydantic import BaseModel

# --- Auth ---
class LoginRequest(BaseModel):
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# --- Picks ---
class TakePickRequest(BaseModel):
    actual_entry: float
    actual_shares: float

class SkipPickRequest(BaseModel):
    reason: Optional[str] = None

# --- Trades ---
class CloseTradeRequest(BaseModel):
    exit_price: float
    exit_date: Optional[str] = None
    notes: Optional[str] = None

class TrimTradeRequest(BaseModel):
    shares_sold: float
    exit_price: float
    reason: Optional[str] = None

class EditTradeRequest(BaseModel):
    actual_entry: Optional[float] = None
    actual_shares: Optional[float] = None
    my_notes: Optional[str] = None

class ReopenRequest(BaseModel):
    pass

# --- Settings ---
class SettingsPatchRequest(BaseModel):
    starting_capital: Optional[float] = None
    accent_color: Optional[str] = None

# --- Daily Watch ---
class WatchTriggerRequest(BaseModel):
    pass

# --- AI ---
class PreMortemRequest(BaseModel):
    run_id: int
