# Video Generation FastAPI Service

This service replicates and extends the video generation logic previously implemented in Node.js/TypeScript.
It accepts image URLs and an audio URL, generates a video with effects (slideshow, zoom, overlay) and background audio, uploads the result to Supabase Storage, and updates a Supabase database table.

## Features

*   **FastAPI Backend:** Built using the modern Python web framework FastAPI.
*   **Background Tasks:** Video generation runs as a background task, allowing the API to respond immediately.
*   **Modular Structure:** Code is organized into modules for configuration, models, services, and utilities.
*   **FFmpeg Integration:** Uses `ffmpeg` (via `asyncio.subprocess`) for video processing (slideshow, zoom, concatenation, overlay, audio mixing).
*   **Supabase Integration:**
    *   Uploads final videos to Supabase Storage.
    *   Creates and updates records in a Supabase database table (`videos`) to track status.
*   **Asynchronous Operations:** Uses `asyncio`, `aiohttp`, and `aiofiles` for efficient I/O operations (downloads, file writing).
*   **Configuration:** Uses `.env` file for sensitive credentials (Supabase URL/Key) via `python-dotenv` and `pydantic-settings`.

## Project Structure

```
video-generator-fastapi/
├── app/
│   ├── core/
│   │   └── config.py       # Configuration loading (env vars)
│   ├── models/
│   │   └── video.py        # Pydantic models (request, response, DB)
│   ├── services/
│   │   ├── supabase_service.py # Supabase client, storage, DB interactions
│   │   └── video_service.py  # Main video generation background task logic
│   ├── utils/
│   │   ├── ffmpeg_utils.py   # Async FFmpeg command runner
│   │   └── file_utils.py     # Async download, file/dir operations
│   └── main.py             # FastAPI app, endpoints, background task scheduling
├── public/
│   └── generated-videos/   # Local storage for generated videos (optional)
├── .env.example            # Example environment variables
├── .gitignore              # Git ignore file
├── README.md               # This file
└── requirements.txt        # Python dependencies
```

## Prerequisites

*   **Python 3.8+**
*   **FFmpeg:** Must be installed on the system where the service runs and accessible in the system's PATH.
*   **Supabase Account:** You need a Supabase project URL, service role key, and a Storage bucket.

## Setup

1.  **Clone the repository (or create the structure):**
    ```bash
    # git clone <your-repo-url> # If applicable
    cd video-generator-fastapi
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure environment variables:**
    *   Copy `.env.example` to `.env`:
        ```bash
        cp .env.example .env
        ```
    *   Edit `.env` and add your Supabase URL, Service Role Key, and Bucket Name.

5.  **Place Dust Overlay File:**
    *   Ensure you have a video file named `dust_overlay.mp4` (or whatever you set in `.env`) in the `video-generator-fastapi` project root directory.

6.  **Set up Supabase Database:**
    *   Connect to your Supabase project's SQL editor.
    *   Run the SQL commands commented out in `app/main.py` to create the `videos` table and optionally the update trigger and indexes.
    *   Make sure the `uuid-ossp` extension is enabled.

## Running the Service

```bash
cd video-generator-fastapi 
# Activate venv if not already active: source venv/bin/activate 

# Run using uvicorn (with auto-reload for development)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.

## API Endpoint

*   **`POST /create-video`**
    *   **Request Body:**
        ```json
        {
          "user_id": "some_user_identifier",
          "image_urls": [
            "https://<your-supabase-url>/storage/v1/object/public/images/image1.jpg",
            "https://<your-supabase-url>/storage/v1/object/public/images/image2.png"
            // ... up to 20 images
          ],
          "audio_url": "https://<your-supabase-url>/storage/v1/object/public/audio/background.mp3"
        }
        ```
    *   **Success Response (202 Accepted):**
        ```json
        {
          "message": "Video creation started successfully. It will be processed in the background.",
          "video_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" 
        }
        ```
    *   **Error Responses:** Standard FastAPI HTTPExceptions (400, 500, 503).

## Notes

*   **Error Handling:** The background task includes basic error handling. Errors during processing will update the database record status to `failed` with an error message.
*   **FFmpeg Paths:** Ensure `ffmpeg` is correctly installed and accessible in the environment's PATH where the FastAPI application is running.
*   **Resource Usage:** Video processing is resource-intensive (CPU, potentially RAM). Monitor your server/container resources.
*   **Scalability:** For production, consider deploying this service using a proper ASGI server like Uvicorn managed by Gunicorn or systemd, potentially behind a reverse proxy like Nginx. For handling many concurrent requests reliably, look into task queues like Celery with Redis/RabbitMQ instead of FastAPI's `BackgroundTasks`.
*   **Supabase Client:** The current implementation creates a single Supabase client instance on startup. For higher load, connection pooling might be considered if using a direct Postgres connection library instead of/alongside `supabase-py`. 