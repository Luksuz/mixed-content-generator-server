import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv() # Load variables from .env file

class Settings(BaseSettings):
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_key: str = os.getenv("SUPABASE_KEY", "")
    supabase_bucket_name: str = os.getenv("SUPABASE_BUCKET_NAME", "video-generator")
    dust_overlay_file_name: str = os.getenv("DUST_OVERLAY_FILE_NAME", "output.webm")
    temp_dir_base: str = os.path.join(os.getcwd(), "temp-video-processing")
    output_dir: str = os.path.join(os.getcwd(), "public", "generated-videos")
    subtitle_font_file: str = os.getenv("SUBTITLE_FONT_FILE", "noto-sans.ttf")
    whisper_model: str = os.getenv("WHISPER_MODEL_NAME", "base")

    # Constants (can be moved to config if they need to be configurable)
    target_video_width: int = 1024
    target_video_height: int = 720
    target_fps: int = 30

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

settings = Settings() 