import asyncio
import logging
import json # Added for potential future JSON parsing if needed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def run_ffmpeg_async(args: list[str], process_name: str) -> tuple[bool, str, str]:
    """Runs an FFmpeg command asynchronously and returns success status, stdout, and stderr."""
    command_str = f"ffmpeg {' '.join(args)}"
    logger.info(f"Starting FFmpeg for {process_name} with args: {command_str}")
    
    process = await asyncio.create_subprocess_exec(
        'ffmpeg', *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout_bytes, stderr_bytes = await process.communicate()
    stdout = stdout_bytes.decode('utf-8', errors='ignore')
    stderr = stderr_bytes.decode('utf-8', errors='ignore')

    log_output = f"\n--- STDOUT ---\n{stdout}\n--- STDERR ---\n{stderr}\n--------------"

    if process.returncode == 0:
        logger.info(f"FFmpeg process for {process_name} finished successfully (Code: 0). Output:{log_output}")
        return True, stdout, stderr
    else:
        logger.error(f"FFmpeg process for {process_name} failed (Code: {process.returncode}). Output:{log_output}")
        return False, stdout, stderr

async def get_media_duration(file_path: str) -> float | None:
    """Gets the duration of a media file in seconds using ffprobe."""
    args = [
        'ffprobe',
        '-v', 'error',             # Only show errors
        '-show_entries', 'format=duration', # Request duration from format section
        '-of', 'default=noprint_wrappers=1:nokey=1', # Output only the value
        file_path
    ]
    command_str = f"ffprobe {' '.join(args)}"
    logger.info(f"Running: {command_str}")

    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    stdout_bytes, stderr_bytes = await process.communicate()
    stdout = stdout_bytes.decode('utf-8', errors='ignore').strip()
    stderr = stderr_bytes.decode('utf-8', errors='ignore').strip()

    if process.returncode == 0 and stdout:
        try:
            duration = float(stdout)
            logger.info(f"Successfully obtained duration for {file_path}: {duration:.2f} seconds")
            return duration
        except ValueError:
            logger.error(f"ffprobe returned non-numeric duration for {file_path}: '{stdout}'")
            return None
    else:
        logger.error(f"ffprobe failed for {file_path} (Code: {process.returncode}). Stderr: {stderr}")
        return None 