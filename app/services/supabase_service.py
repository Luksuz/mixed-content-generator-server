import os
import logging
from supabase import create_client, Client
from core.config import settings
from typing import Optional

logger = logging.getLogger(__name__)

def get_supabase_client() -> Optional[Client]:
    """Initializes and returns a Supabase client instance."""
    if not settings.supabase_url or not settings.supabase_key:
        logger.error("Supabase URL or Key not configured. Cannot initialize client.")
        return None
    try:
        client: Client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client initialized successfully.")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Supabase client: {e}")
        return None

supabase_client = get_supabase_client()

async def upload_to_supabase_storage(file_path: str, destination_path: str) -> Optional[str]:
    """Uploads a file to Supabase Storage and returns the public URL."""
    if not supabase_client:
        logger.error("Supabase client not available for storage upload.")
        return None
    
    try:
        logger.info(f"Uploading {file_path} to Supabase Storage at {settings.supabase_bucket_name}/{destination_path}")
        with open(file_path, 'rb') as f:
            # Use upsert=True to overwrite if file exists (optional)
            res = supabase_client.storage.from_(settings.supabase_bucket_name).upload(
                path=destination_path,
                file=f,
                file_options={"content-type": "video/mp4", "upsert": "true"} 
            )

        print("*****************")
        print(res)
        print("*****************")
        
        if res.fullPath:
             # Construct the public URL manually or use get_public_url if your bucket is public
            public_url = f"{settings.supabase_url}/storage/v1/object/public/{settings.supabase_bucket_name}/{destination_path}"
            # Or use: public_url = supabase_client.storage.from_(settings.supabase_bucket_name).get_public_url(destination_path)
            logger.info(f"✅ Successfully uploaded to Supabase Storage. Public URL: {public_url}")
            return public_url
        else:
            logger.error(f"❌ Failed to upload to Supabase Storage. Status: {res.status_code}, Response: {res.text}")
            return None
    except Exception as e:
        logger.error(f"Error uploading file {file_path} to Supabase Storage: {e}")
        return None

async def update_video_record_status(
    video_id: str, 
    status: str, 
    final_video_url: Optional[str] = None, 
    error_message: Optional[str] = None,
    minutes_taken: Optional[float] = None
):
    """Updates the status and potentially the final URL, error message, or minutes_taken of a video record in the database."""
    if not supabase_client:
        logger.error("Supabase client not available for database update.")
        return

    update_data = {
        "status": status,
        "final_video_url": final_video_url,
        "error_message": error_message,
        "minutes_taken": minutes_taken
    }
    # Remove None values so they don't overwrite existing DB values unexpectedly
    update_data = {k: v for k, v in update_data.items() if v is not None}

    try:
        logger.info(f"Updating video record {video_id} with data: {update_data}")
        # Replace 'videos' with your actual table name
        data, count = supabase_client.table('video_records')\
                                    .update(update_data)\
                                    .eq('id', video_id)\
                                    .execute()
        
        # Check if the update was successful (depends on execute() return type/behavior)
        # Supabase-py V1 might return a list like [[record], count] or similar
        # Supabase-py V2 returns an APIResponse object
        # Adjust error checking based on the version you are using
        # Example for V2 (check if data is present in response):
        # if not data or (isinstance(data, list) and not data[0]):
        #     logger.warning(f"No record found or updated for video_id: {video_id}")
        # else:
        #     logger.info(f"Successfully updated video record {video_id}")
        # Generic log for now:
        logger.info(f"Database update response for {video_id}: Data={data}, Count={count}")

    except Exception as e:
        logger.error(f"Error updating video record {video_id} in database: {e}")

# Placeholder for creating the initial record (called from main.py)
async def create_initial_video_record(video_data: dict) -> Optional[str]:
    """Creates an initial record in the database and returns the new record's ID."""
    if not supabase_client:
        logger.error("Supabase client not available for database insert.")
        return None
    try:
        logger.info(f"Creating initial video record with data: {video_data}")
        # Replace 'videos' with your actual table name
        data, count = supabase_client.table('video_records').insert(video_data).execute()
        
        # Extract ID from the response data structure
        print(type(data))


        if data and isinstance(data, tuple) and data[0]:
            record_id = data[1][0]['id']  # Access the first record in the data array
            logger.info(f"Successfully created initial video record with ID: {record_id}")
            return str(record_id)  # Ensure it's returned as string if needed
        else:
            logger.error(f"Failed to create initial video record or extract ID. Response: {data}")
            return None

    except Exception as e:
        logger.error(f"Error creating initial video record in database: {e}")
        return None 