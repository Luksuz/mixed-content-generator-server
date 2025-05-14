from fastapi import FastAPI, BackgroundTasks, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import logging
import uuid

from models.video import CreateVideoRequest, CreateVideoResponse, VideoRecord
from services.video_service import create_video_task
from services.supabase_service import create_initial_video_record, supabase_client
from core.config import settings
from utils.file_utils import ensure_dir

# --- Logging Setup --- 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- FastAPI App Initialization --- 
app = FastAPI(title="Video Generation Service")

# --- Mount Static Files Directory (Optional) ---
# Serve files from the 'public' directory (where videos might be stored locally)
ensure_dir(settings.output_dir) # Ensure the directory exists before mounting
app.mount("/public", StaticFiles(directory=settings.output_dir), name="public")

# --- Database Schema (Commented Out SQL) --- 
# Ensure you have the uuid-ossp extension enabled in Supabase/Postgres:
# CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
# 
# CREATE TABLE IF NOT EXISTS videos (
#     id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
#     user_id TEXT NOT NULL,                 -- Or VARCHAR, depending on your user ID format
#     image_urls TEXT[] NOT NULL,            -- Store as an array of strings
#     audio_url TEXT NOT NULL,
#     status VARCHAR(20) NOT NULL DEFAULT 'pending', -- e.g., pending, processing, completed, failed
#     final_video_url TEXT,
#     error_message TEXT,
#     created_at TIMESTAMPTZ DEFAULT timezone('utc', now()) NOT NULL,
#     updated_at TIMESTAMPTZ DEFAULT timezone('utc', now()) NOT NULL
# );
# 
# -- Optional: Trigger to automatically update updated_at timestamp
# CREATE OR REPLACE FUNCTION trigger_set_timestamp()
# RETURNS TRIGGER AS $$
# BEGIN
#   NEW.updated_at = timezone('utc', now());
#   RETURN NEW;
# END;
# $$ LANGUAGE plpgsql;
# 
# CREATE TRIGGER set_videos_timestamp
# BEFORE UPDATE ON videos
# FOR EACH ROW
# EXECUTE FUNCTION trigger_set_timestamp();
#
# -- Optional: Index for querying by user_id or status
# CREATE INDEX IF NOT EXISTS idx_videos_user_id ON videos(user_id);
# CREATE INDEX IF NOT EXISTS idx_videos_status ON videos(status);

# --- API Endpoints --- 
@app.get("/")
async def read_root():
    return {"message": "Video Generation API is running."}

@app.post("/create-video", response_model=CreateVideoResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_video_endpoint(request: CreateVideoRequest, background_tasks: BackgroundTasks):
    """Accepts video creation requests and starts the process in the background."""
    logger.info(f"Received video creation request for user: {request.user_id}")

    if not supabase_client:
        logger.error("Supabase client is not initialized. Cannot process request.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
            detail="Video processing service is temporarily unavailable."
        )

    if not request.image_urls:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Image URLs cannot be empty.")
        
    if len(request.image_urls) > 20: # Limit number of images
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot process more than 20 images.")

    # 1. Create an initial record in the database
    video_record = VideoRecord(
        user_id=request.user_id,
        image_urls=[str(url) for url in request.image_urls], # Convert HttpUrl to str for DB
        audio_url=str(request.audio_url),
        status="pending" # Initial status
    )
    
    # Use .dict() or .model_dump() depending on Pydantic version
    # record_data = video_record.model_dump(exclude_unset=True) 
    record_data = video_record.dict(exclude_unset=True) # For Pydantic v1
    record_data['id'] = str(video_record.id) # Ensure UUID is string for Supabase insert if needed

    video_id = await create_initial_video_record(record_data)

    if not video_id:
        logger.error("Failed to create initial video record in database.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Failed to initiate video creation process."
        )

    logger.info(f"Initial video record created with ID: {video_id}")

    # 2. Add the video generation task to the background
    background_tasks.add_task(
        create_video_task,
        video_id=video_id,
        user_id=request.user_id,
        image_urls=[str(url) for url in request.image_urls], # Pass URLs as strings
        audio_url=str(request.audio_url)
    )

    logger.info(f"Video creation task for ID {video_id} added to background.")

    # 3. Return acceptance response
    return CreateVideoResponse(
        message="Video creation started successfully. It will be processed in the background.",
        video_id=video_record.id # Return the generated UUID
    )

# --- Uvicorn Runner (for local development) --- 
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server...")
    # Use reload=True for development to automatically reload on code changes
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 