import secrets
from datetime import datetime
from app import db, login_manager
from flask_login import UserMixin


class IPPool(db.Model):
    __tablename__ = 'ip_pool'

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), unique=True, nullable=False, index=True)
    free_credits = db.Column(db.Integer, nullable=False, default=85)
    total_used = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_reset = db.Column(db.DateTime, default=datetime.utcnow)

    def deduct(self, amount):
        if self.free_credits >= amount:
            self.free_credits -= amount
            self.total_used += amount
            return True
        return False


class ToolCost(db.Model):
    __tablename__ = 'tool_costs'

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(50), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    credit_cost = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    is_paid_only = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text, default='')
    price_multiplier = db.Column(db.Float, default=1.0)


class UsageLog(db.Model):
    __tablename__ = 'usage_log'

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    tool_slug = db.Column(db.String(50), nullable=False)
    credits_spent = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class UserInteraction(db.Model):
    __tablename__ = 'user_interaction'

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    session_id = db.Column(db.String(64), nullable=True)
    action_type = db.Column(db.String(50), nullable=False)
    page = db.Column(db.String(255), nullable=True)
    detail = db.Column(db.Text, nullable=True)
    duration_ms = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class ApiKey(db.Model):
    __tablename__ = 'api_key'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    rate_limit = db.Column(db.Integer, default=60)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime, nullable=True)
    total_requests = db.Column(db.Integer, default=0)

    @staticmethod
    def generate_key():
        return 'nf_' + secrets.token_hex(32)


class OllamaInstance(db.Model):
    __tablename__ = 'ollama_instance'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(255), nullable=False)
    api_key = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    priority = db.Column(db.Integer, default=0)
    fail_count = db.Column(db.Integer, default=0)
    last_check = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    models = db.relationship('OllamaModel', backref='instance', lazy='dynamic', cascade='all, delete-orphan')


class OllamaModel(db.Model):
    __tablename__ = 'ollama_model'

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer, db.ForeignKey('ollama_instance.id'), nullable=False)
    model_name = db.Column(db.String(100), nullable=False)
    is_free = db.Column(db.Boolean, default=True)
    credit_cost = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    requires_paid_account = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AppConfig(db.Model):
    __tablename__ = 'app_config'

    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get(cls, key, default=None):
        obj = cls.query.get(key)
        return obj.value if obj else default

    @classmethod
    def set(cls, key, value):
        obj = cls.query.get(key)
        if obj:
            obj.value = value
        else:
            obj = cls(key=key, value=value)
            db.session.add(obj)
        db.session.commit()


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(256))
    is_paid = db.Column(db.Boolean, default=False)
    subscription_tier = db.Column(db.String(20), default='free')
    api_key = db.Column(db.String(64), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    credit_bonus = db.Column(db.Integer, default=0)


class Payment(db.Model):
    __tablename__ = 'payment'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    amount = db.Column(db.Float)
    stripe_session_id = db.Column(db.String(128))
    status = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def seed_tool_costs():
    if ToolCost.query.first() is not None:
        return

    tools = [
        ('chat', 'AI Chat', 'chat', 5, False, 'Chat with AI assistant'),
        ('ocr', 'Document OCR', 'document', 10, False, 'Extract text from documents and images'),
        ('image-gen', 'Image Generation', 'image', 20, False, 'Generate images from text prompts'),
        ('image-edit', 'Image Editing', 'image', 15, False, 'Edit images with AI'),
        ('document-convert', 'Document Convert', 'document', 8, False, 'Convert between document formats'),
        ('document-translate', 'Document Translate', 'document', 10, False, 'Translate documents to other languages'),
        ('document-sign', 'Digital Signatures', 'document', 12, False, 'Sign documents digitally'),
        ('transcribe', 'Audio Transcription', 'audio', 10, False, 'Transcribe audio to text'),
        ('tts', 'Text to Speech', 'audio', 3, False, 'Convert text to natural speech'),
        ('stt', 'Speech to Text', 'audio', 8, False, 'Convert speech to text'),
        ('video-transcribe', 'Video Transcription', 'video', 20, False, 'Transcribe video audio to text'),
        ('video-analyze', 'Video Analysis', 'video', 25, False, 'Analyze video content with AI'),
        ('detect', 'Object Detection', 'image', 15, False, 'Detect objects in images'),
        ('segment', 'Image Segmentation', 'image', 20, False, 'Segment objects in images'),
        ('pose', 'Pose Detection', 'image', 10, False, 'Detect human poses in images'),
        ('code-gen', 'Code Generation', 'development', 10, False, 'Generate code with AI'),
        ('code-exec', 'Code Execution', 'development', 15, False, 'Execute code in sandbox'),
        ('code-review', 'Code Review', 'development', 8, False, 'Review code with AI'),
        ('form-build', 'Form Builder', 'forms', 12, False, 'Build custom forms'),
        ('resume-build', 'Resume Builder', 'forms', 8, False, 'Build professional resumes'),
        ('cover-letter', 'Cover Letter', 'forms', 5, False, 'Generate cover letters'),
        ('legal-template', 'Legal Templates', 'forms', 15, False, 'Generate legal document templates'),
    ]

    for slug, name, category, cost, paid_only, desc in tools:
        db.session.add(ToolCost(
            slug=slug, name=name, category=category,
            credit_cost=cost, is_paid_only=paid_only, description=desc
        ))
    db.session.commit()

    if ApiKey.query.first() is None:
        key = ApiKey(
            key=ApiKey.generate_key(),
            name='Default Admin Key',
            is_active=True,
        )
        db.session.add(key)
        db.session.commit()


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
