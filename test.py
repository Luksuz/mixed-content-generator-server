from openai import OpenAI

client = OpenAI()
audio_file = open("audio.mp3", "rb")

transcription = client.audio.transcriptions.create(
    model="whisper-1", 
    file=audio_file, 
    response_format="srt"
)

print(transcription)