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
    subtitle_font_file: str = os.getenv("SUBTITLE_FONT_FILE", "montserrat.ttf")
    whisper_model: str = os.getenv("WHISPER_MODEL_NAME", "base")
    
    # Zoom settings
    use_high_quality_zoom: bool = os.getenv("USE_HIGH_QUALITY_ZOOM", True)
    hq_zoom_input_framerate: int = os.getenv("HQ_ZOOM_INPUT_FRAMERATE", 25)
    hq_zoom_output_framerate: int = os.getenv("HQ_ZOOM_OUTPUT_FRAMERATE", 25)
    hq_zoom_initial_scale: int = os.getenv("HQ_ZOOM_INITIAL_SCALE", 4000) # Width for initial upscale
    # Settings for alternating (ping-pong) zoom
    hq_zoom_pingpong_increment: float = os.getenv("HQ_ZOOM_PINGPONG_INCREMENT", 0.0015)
    hq_zoom_pingpong_duration_s: int = os.getenv("HQ_ZOOM_PINGPONG_DURATION_S", 20) # Duration for one direction (in or out)
    hq_zoom_max_factor: float = os.getenv("HQ_ZOOM_MAX_FACTOR", 1.5) # Max zoom level (e.g., 1.5x)
    # hq_zoom_increment is deprecated by hq_zoom_pingpong_increment if using alternating zoom
    # hq_zoom_max_scale is not directly used by zoompan z factor, hq_zoom_max_factor is used.

    srt_max_words_per_line: int = os.getenv("SRT_MAX_WORDS_PER_LINE", 4)
    
    # FFmpeg encoding settings
    ffmpeg_preset: str = os.getenv("FFMPEG_PRESET", "medium")
    ffmpeg_crf: int = os.getenv("FFMPEG_CRF", 23)
    ffmpeg_audio_bitrate: str = os.getenv("FFMPEG_AUDIO_BITRATE", "192k") # Added for completeness
    
    # Subtitle styling parameters
    subtitle_font_size: str = os.getenv("SUBTITLE_FONT_SIZE", "24") # Kept as string from previous edit
    subtitle_primary_colour: str = os.getenv("SUBTITLE_PRIMARY_COLOUR", "&H00FFFFFF&") # White, leading 00 for Alpha
    subtitle_outline_colour: str = os.getenv("SUBTITLE_OUTLINE_COLOUR", "&H00000000&") # Black, leading 00 for Alpha
    subtitle_border_style: str = os.getenv("SUBTITLE_BORDER_STYLE", "1") # 1=outline
    subtitle_outline_thickness: str = os.getenv("SUBTITLE_OUTLINE_THICKNESS", "2.0")
    subtitle_margin_v: str = os.getenv("SUBTITLE_MARGIN_V", "30")
    subtitle_wrap_style: str = os.getenv("SUBTITLE_WRAP_STYLE", "2") # 2=no word wrap
    
    # Target video properties
    target_video_width: int = 1024
    target_video_height: int = 720
    target_fps: int = 30 # For non-HQ zoom parts and slideshow

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'

settings = Settings() 