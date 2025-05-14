import os
import asyncio
import whisper # type: ignore
from datetime import timedelta # Keep for reference, but direct ms calculation is better

# Consider loading the model globally in a production app for efficiency
# WHISPER_MODEL = None
# def get_whisper_model(model_name="base"):
#     global WHISPER_MODEL
#     if WHISPER_MODEL is None:
#         WHISPER_MODEL = whisper.load_model(model_name)
#         # logger.info(f"Whisper model '{model_name}' loaded globally.")
#     return WHISPER_MODEL

def _blocking_transcribe_and_save(audio_path: str, output_srt_path: str, model_name: str = "base") -> bool:
    """
    Performs audio transcription using Whisper and saves it as an SRT file.
    This is a blocking function and should be run in a thread.
    """
    try:
        # model = get_whisper_model(model_name) # Use if global model loading is implemented
        model = whisper.load_model(model_name) # Load model per call for now
        
        # logger.info(f"Starting transcription for: {audio_path}")
        transcribe_result = model.transcribe(audio=audio_path, verbose=False)
        segments = transcribe_result['segments']

        if os.path.exists(output_srt_path):
            os.remove(output_srt_path) # Overwrite if exists

        with open(output_srt_path, 'w', encoding='utf-8') as srtFile:
            for segment in segments:
                s_total_start = segment['start']
                hrs_start = int(s_total_start / 3600)
                mins_start = int((s_total_start % 3600) / 60)
                secs_start = int(s_total_start % 60)
                ms_start = int((s_total_start % 1) * 1000)
                startTime = f"{hrs_start:02d}:{mins_start:02d}:{secs_start:02d},{ms_start:03d}"

                s_total_end = segment['end']
                hrs_end = int(s_total_end / 3600)
                mins_end = int((s_total_end % 3600) / 60)
                secs_end = int(s_total_end % 60)
                ms_end = int((s_total_end % 1) * 1000)
                endTime = f"{hrs_end:02d}:{mins_end:02d}:{secs_end:02d},{ms_end:03d}"
                
                text = segment['text'].strip()
                segmentId = segment['id'] + 1  # Whisper IDs are 0-indexed
                
                segment_line = f"{segmentId}\n{startTime} --> {endTime}\n{text}\n\n"
                srtFile.write(segment_line)
        
        # logger.info(f"SRT file generated successfully: {output_srt_path}")
        return True
    except Exception as e:
        # logger.error(f"Error during transcription for {audio_path}: {e}", exc_info=True)
        print(f"Error during transcription for {audio_path}: {e}") # Placeholder for logger
        return False

async def generate_srt_from_audio(audio_path: str, output_srt_path: str, model_name: str = "base") -> bool:
    """
    Asynchronously generates an SRT file from an audio path using Whisper.
    """
    # logger.debug(f"Queueing transcription for {audio_path} to SRT {output_srt_path}")
    return await asyncio.to_thread(_blocking_transcribe_and_save, audio_path, output_srt_path, model_name) 