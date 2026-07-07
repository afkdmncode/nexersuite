import os
import sys
import json
import logging
import logging.handlers
from datetime import datetime
from functools import wraps

LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
        }
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        if record.exc_info and record.exc_info[0]:
            log_entry['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


def _make_handler(filename, level=logging.DEBUG, max_bytes=10*1024*1024, backup_count=5):
    path = os.path.join(LOG_DIR, filename)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backup_count
    )
    handler.setLevel(level)
    handler.setFormatter(JSONFormatter())
    return handler


app_log = logging.getLogger('novaforge')
app_log.setLevel(logging.DEBUG)
app_log.addHandler(_make_handler('app.log'))
app_log.addHandler(_make_handler('errors.log', logging.ERROR))

request_log = logging.getLogger('novaforge.request')
request_log.setLevel(logging.DEBUG)
request_log.addHandler(_make_handler('requests.log'))
request_log.propagate = False

credit_log = logging.getLogger('novaforge.credit')
credit_log.setLevel(logging.DEBUG)
credit_log.addHandler(_make_handler('credits.log'))
credit_log.propagate = False

admin_log = logging.getLogger('novaforge.admin')
admin_log.setLevel(logging.DEBUG)
admin_log.addHandler(_make_handler('admin.log'))
admin_log.propagate = False

tool_log = logging.getLogger('novaforge.tool')
tool_log.setLevel(logging.DEBUG)
tool_log.addHandler(_make_handler('tools.log'))
tool_log.propagate = False

user_log = logging.getLogger('novaforge.user')
user_log.setLevel(logging.DEBUG)
user_log.addHandler(_make_handler('users.log'))
user_log.propagate = False

error_log = logging.getLogger('novaforge.error')
error_log.setLevel(logging.ERROR)
error_log.addHandler(_make_handler('errors.log'))
error_log.propagate = False


def log_with_fields(logger, level, message, **fields):
    record = logger.makeRecord(
        logger.name, logging._nameToLevel[level.upper()],
        None, 0, message, None, None
    )
    record.extra_fields = fields
    logger.handle(record)


def log_request(method, path, status, duration_ms, ip, user_agent, **extra):
    log_with_fields(request_log, 'info', f'{method} {path} {status}',
                    method=method, path=path, status=status,
                    duration_ms=duration_ms, ip=ip, user_agent=user_agent,
                    **extra)


def log_credit(ip, action, tool_slug, credits, remaining, user_id=None):
    log_with_fields(credit_log, 'info', f'{action} {tool_slug}',
                    ip=ip, action=action, tool=tool_slug,
                    credits=credits, remaining=remaining,
                    user_id=str(user_id) if user_id else 'anonymous')


def log_admin(action, admin_ip, details=None):
    log_with_fields(admin_log, 'info', f'Admin: {action}',
                    admin_ip=admin_ip, action=action,
                    details=json.dumps(details) if details else '')


def log_tool_usage(tool_slug, ip, status, duration_ms, credits_cost=0, **extra):
    log_with_fields(tool_log, 'info', f'{tool_slug} {status}',
                    tool=tool_slug, ip=ip, status=status,
                    duration_ms=duration_ms, credits=credits_cost,
                    **extra)


def log_user_action(ip, action_type, page=None, detail=None, user_id=None, session_id=None, duration_ms=0):
    log_with_fields(user_log, 'info', f'{action_type} {page or ""}',
                    ip=ip, action=action_type, page=page,
                    detail=detail, user_id=str(user_id) if user_id else 'anonymous',
                    session_id=session_id or '', duration_ms=duration_ms)


def log_error(message, **fields):
    log_with_fields(error_log, 'error', message, **fields)
    app_log.error(message, extra={'extra_fields': fields})


def get_recent_logs(log_type='app', lines=100):
    files = {
        'app': 'app.log',
        'requests': 'requests.log',
        'credits': 'credits.log',
        'admin': 'admin.log',
        'tools': 'tools.log',
        'users': 'users.log',
        'errors': 'errors.log',
    }
    path = os.path.join(LOG_DIR, files.get(log_type, 'app.log'))
    if not os.path.exists(path):
        return []
    try:
        with open(path) as f:
            all_lines = f.readlines()
            return [json.loads(l) for l in all_lines[-lines:] if l.strip()]
    except (json.JSONDecodeError, Exception) as e:
        return [{'error': str(e), 'raw': l} for l in all_lines[-lines:] if l.strip()]


def get_log_stats():
    stats = {}
    for name in ('app', 'requests', 'credits', 'admin', 'tools', 'users', 'errors'):
        path = os.path.join(LOG_DIR, f'{name}.log')
        if os.path.exists(path):
            size = os.path.getsize(path)
            with open(path) as f:
                line_count = sum(1 for _ in f)
            stats[name] = {'size_bytes': size, 'size_mb': round(size / 1024 / 1024, 2), 'lines': line_count}
        else:
            stats[name] = {'size_bytes': 0, 'size_mb': 0, 'lines': 0}
    return stats
