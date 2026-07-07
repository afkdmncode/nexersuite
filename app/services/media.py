import io
import os
import tempfile
import subprocess
from gtts import gTTS


def text_to_speech(text, lang='en', slow=False):
    tts = gTTS(text=text, lang=lang, slow=slow)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp


def transcribe_audio(file_bytes):
    """Transcribe audio to text using SpeechRecognition."""
    try:
        import speech_recognition as sr
    except ImportError:
        raise RuntimeError('SpeechRecognition not installed. Run: pip install SpeechRecognition')

    r = sr.Recognizer()

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        with sr.AudioFile(tmp_path) as source:
            audio = r.record(source)

        try:
            text = r.recognize_google(audio)
        except sr.UnknownValueError:
            text = ''
        except sr.RequestError:
            text = r.recognize_sphinx(audio)
    finally:
        os.unlink(tmp_path)

    return text


def speech_to_text(file_bytes):
    """Alias for transcribe_audio."""
    return transcribe_audio(file_bytes)


def translate_audio(file_bytes, target_language='en'):
    """Transcribe audio then translate the text."""
    text = transcribe_audio(file_bytes)

    if target_language == 'en':
        return text

    from app.services.ai import translate_text
    return translate_text(text, target_language)


def transcribe_video(file_bytes):
    """Extract audio from video and transcribe to text."""
    try:
        import speech_recognition as sr
    except ImportError:
        raise RuntimeError('SpeechRecognition not installed')

    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_v:
        tmp_v.write(file_bytes)
        video_path = tmp_v.name

    audio_path = tempfile.mktemp(suffix='.wav')

    try:
        result = subprocess.run(
            ['ffmpeg', '-i', video_path, '-q:a', '0', '-map', 'a', audio_path,
             '-y', '-loglevel', 'error'],
            capture_output=True, timeout=120
        )
        if result.returncode != 0:
            raise RuntimeError(f'ffmpeg failed: {result.stderr.decode()}')

        r = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            audio = r.record(source)

        try:
            text = r.recognize_google(audio)
        except sr.UnknownValueError:
            text = ''
        except sr.RequestError:
            text = r.recognize_sphinx(audio)
    finally:
        os.unlink(video_path)
        if os.path.exists(audio_path):
            os.unlink(audio_path)

    return text
