from gtts import gTTS
import io


def text_to_speech(text, lang='en', slow=False):
    tts = gTTS(text=text, lang=lang, slow=slow)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp


def transcribe_audio(file_bytes):
    raise NotImplementedError('Audio transcription coming soon')


def speech_to_text(file_bytes):
    raise NotImplementedError('Speech to text coming soon')


def translate_audio(file_bytes, target_language='en'):
    raise NotImplementedError('Audio translation coming soon')


def transcribe_video(file_bytes):
    raise NotImplementedError('Video transcription coming soon')
