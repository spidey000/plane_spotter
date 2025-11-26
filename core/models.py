from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

class FlightStatus(str, Enum):
    SCHEDULED = "scheduled"
    EN_ROUTE = "en_route"
    LANDED = "landed"
    UNKNOWN = "unknown"

class Flight(BaseModel):
    flight_id: str = Field(..., description="Unique identifier for the flight from the provider")
    flight_name: Optional[str] = None
    flight_name_iata: Optional[str] = None
    registration: Optional[str] = None
    aircraft_name: Optional[str] = None
    aircraft_icao: Optional[str] = None
    airline_name: Optional[str] = None
    airline_icao: Optional[str] = None
    origin_name: Optional[str] = None
    origin_icao: Optional[str] = None
    destination_name: Optional[str] = None
    destination_icao: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    actual_time: Optional[datetime] = None
    status: FlightStatus = FlightStatus.UNKNOWN
    diverted: bool = False
    terminal: Optional[str] = None
    gate: Optional[str] = None
    
    # Metadata
    source: str = Field(..., description="Source of the data (e.g., 'aeroapi', 'adb')")
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Raw data from the provider")

class InterestingReason(BaseModel):
    reason_code: str # e.g., "MODEL", "REGISTRATION", "FIRST_SEEN"
    description: str
    details: Optional[str] = None

class ProcessedFlight(BaseModel):
    flight: Flight
    is_interesting: bool = False
    reasons: List[InterestingReason] = Field(default_factory=list)
    image_url: Optional[str] = None
    photographer: Optional[str] = None
    check_flags: Dict[str, int] = Field(default_factory=dict, description="Flags indicating status of various checks (1=Pass/True, 0=Fail/False)")
