import os
import time
from flask import Flask, request, g
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from app.config import Config

db = SQLAlchemy()
login_manager = LoginManager()


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs'), exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'landing.index'

    from app.services.logger import log_request, log_error, app_log

    @app.before_request
    def before_request_logging():
        g.start_time = time.time()
        g.ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown')
        app_log.debug(f'Request: {request.method} {request.path}', extra={
            'extra_fields': {
                'ip': g.ip, 'method': request.method,
                'path': request.path, 'user_agent': request.headers.get('User-Agent', '')
            }
        })

    @app.after_request
    def after_request_logging(response):
        duration = int((time.time() - g.get('start_time', time.time())) * 1000)
        log_request(
            method=request.method, path=request.path,
            status=response.status_code, duration_ms=duration,
            ip=g.get('ip', 'unknown'),
            user_agent=request.headers.get('User-Agent', '')[:120],
            content_length=response.content_length or 0,
        )
        response.headers.add('X-Response-Time', f'{duration}ms')
        return response

    @app.errorhandler(404)
    def not_found(e):
        log_error(f'404: {request.path}', ip=g.get('ip', 'unknown'), path=request.path)
        return {'error': 'Not found'}, 404

    @app.errorhandler(500)
    def server_error(e):
        log_error(f'500: {request.path}', ip=g.get('ip', 'unknown'), path=request.path)
        return {'error': 'Internal server error'}, 500

    from app.routes.landing import landing_bp
    from app.routes.chat import chat_bp
    from app.routes.tools import tools_bp
    from app.routes.api import api_bp
    from app.routes.credits import credits_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(landing_bp)
    app.register_blueprint(chat_bp, url_prefix='/chat')
    app.register_blueprint(tools_bp, url_prefix='/tools')
    app.register_blueprint(api_bp, url_prefix='/api/v1')
    app.register_blueprint(credits_bp, url_prefix='/credits')
    app.register_blueprint(admin_bp)

    with app.app_context():
        from app import models
        db.create_all()
        models.seed_tool_costs()

    app_log.info('NovaForge application started', extra={'extra_fields': {'config': 'loaded'}})

    return app
