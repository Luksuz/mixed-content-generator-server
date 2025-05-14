import os
import asyncio
# import whisper # type: ignore -> No longer using local whisper library
# from datetime import timedelta -> No longer manually building timestamps
from openai import OpenAI # type: ignore
from app.core.config import settings # Import settings

# Ensure OPENAI_API_KEY is set in your environment variables

def _blocking_transcribe_and_save_openai(audio_path: str, output_srt_path: str, model_name: str = "whisper-1") -> bool:
    """
    Performs audio transcription using the OpenAI API (whisper-1 model)
    and saves the SRT response directly to a file.
    This is a blocking function and should be run in a thread.
    """
    try:
        client = OpenAI(api_key=settings.openai_api_key) # Use API key from settings
        # logger.info(f"Starting OpenAI transcription for: {audio_path} using model {model_name}")
        
        with open(audio_path, "rb") as audio_file_object:
            transcription_response = client.audio.transcriptions.create(
                model=model_name, 
                file=audio_file_object, 
                response_format="srt"
            )
        
        # The transcription_response is directly the SRT content as a string
        # Ensure it's a string before writing, though it should be for srt format
        if not isinstance(transcription_response, str):
            # logger.error(f"OpenAI transcription did not return a string for SRT format. Got: {type(transcription_response)}")
            print(f"OpenAI transcription did not return a string for SRT format. Got: {type(transcription_response)}")
            return False

        with open(output_srt_path, 'w', encoding='utf-8') as srtFile:
            srtFile.write(transcription_response)
        
        # logger.info(f"SRT file from OpenAI API generated successfully: {output_srt_path}")
        return True
    except Exception as e:
        # logger.error(f"Error during OpenAI transcription for {audio_path}: {e}", exc_info=True)
        print(f"Error during OpenAI transcription for {audio_path}: {e}") # Placeholder for logger
        return False

async def generate_srt_from_audio(audio_path: str, output_srt_path: str, model_name: str = "whisper-1") -> bool:
    """
    Asynchronously generates an SRT file from an audio path using the OpenAI API.
    The model_name parameter should be compatible with OpenAI's transcription models (e.g., "whisper-1").
    """
    # logger.debug(f"Queueing OpenAI transcription for {audio_path} to SRT {output_srt_path} using model {model_name}")
    return await asyncio.to_thread(_blocking_transcribe_and_save_openai, audio_path, output_srt_path, model_name) 