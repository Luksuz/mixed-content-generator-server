import aiohttp
import aiofiles
import os
import shutil
import logging
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

async def download_file(url: str, filepath: str) -> bool:
    """Downloads a file asynchronously from a URL to a local path."""
    logger.info(f"Attempting to download from: {url} to {filepath}")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()  # Raise an exception for bad status codes
                async with aiofiles.open(filepath, mode='wb') as f:
                    while True:
                        chunk = await response.content.read(1024) # Read in chunks
                        if not chunk:
                            break
                        await f.write(chunk)
                logger.info(f"Successfully downloaded and saved file to: {filepath}")
                return True
    except aiohttp.ClientError as e:
        logger.error(f"Error downloading file {url}: {e}")
        return False
    except Exception as e:
        logger.error(f"An unexpected error occurred during download of {url}: {e}")
        return False

def ensure_dir(dir_path: str):
    """Ensures that a directory exists, creating it if necessary."""
    if not os.path.exists(dir_path):
        os.makedirs(dir_path, exist_ok=True)
        logger.info(f"Created directory: {dir_path}")

def cleanup_dir(dir_path: str):
    """Removes a directory and its contents."""
    if os.path.exists(dir_path) and os.path.isdir(dir_path):
        try:
            shutil.rmtree(dir_path)
            logger.info(f"Successfully removed temporary directory: {dir_path}")
        except OSError as e:
            logger.error(f"Error removing directory {dir_path}: {e}")

def get_file_extension_from_url(url: str) -> str:
    """Extracts the file extension from a URL, defaulting to .jpg."""
    try:
        parsed_path = urlparse(url).path
        _, ext = os.path.splitext(parsed_path)
        return ext if ext else '.jpg'
    except Exception:
        logger.warning(f"Could not parse URL to get extension: {url}. Defaulting to .jpg")
        return '.jpg' 