from pydantic import BaseModel, HttpUrl
from typing import List, Optional
import uuid

class CreateVideoRequest(BaseModel):
    user_id: str # Assuming user ID is a string, adjust if it's UUID or int
    image_urls: List[HttpUrl]
    audio_url: HttpUrl

class CreateVideoResponse(BaseModel):
    message: str
    video_id: Optional[uuid.UUID] = None # Return the ID for potential status tracking
    error: Optional[str] = None

# Optional: Model representing the database table structure
class VideoRecord(BaseModel):
    id: uuid.UUID = uuid.uuid4()
    user_id: str
    image_urls: List[str] # Store as list of strings in DB
    audio_url: str
    status: str = "pending" # e.g., pending, processing, completed, failed
    final_video_url: Optional[str] = None
    error_message: Optional[str] = None
    # Add created_at, updated_at if managed by DB 