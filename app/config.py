import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///ai_platform.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
    GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')

    FREE_CREDIT_POOL = int(os.getenv('FREE_CREDIT_POOL', '85'))
    ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin')

    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', '5000'))
    DEBUG = os.getenv('FLASK_ENV', 'development') == 'development'

    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024

    TOOL_COSTS = {
        'chat': 5,
        'ocr': 10,
        'image-gen': 20,
        'image-edit': 15,
        'document-convert': 8,
        'document-translate': 10,
        'document-sign': 12,
        'transcribe': 10,
        'tts': 3,
        'stt': 8,
        'video-transcribe': 20,
        'video-analyze': 25,
        'detect': 15,
        'segment': 20,
        'pose': 10,
        'code-gen': 10,
        'code-exec': 15,
        'code-review': 8,
        'sql-gen': 5,
        'form-build': 12,
        'resume-build': 8,
        'cover-letter': 5,
        'legal-template': 15,
    }
