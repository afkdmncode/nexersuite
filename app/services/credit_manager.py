from functools import wraps
from flask import request, jsonify, session
from app import db
from app.models import IPPool, UsageLog, ToolCost, User
from app.config import Config
from app.services.logger import log_credit, log_error


def get_client_ip():
    if request.headers.get('X-Forwarded-For'):
        return request.headers['X-Forwarded-For'].split(',')[0].strip()
    return request.remote_addr or '127.0.0.1'


def get_free_credits(ip_address=None):
    if ip_address is None:
        ip_address = get_client_ip()
    pool = IPPool.query.filter_by(ip_address=ip_address).first()
    if pool is None:
        pool = IPPool(ip_address=ip_address, free_credits=Config.FREE_CREDIT_POOL)
        db.session.add(pool)
        db.session.commit()
        log_credit(ip_address, 'pool_created', 'none', Config.FREE_CREDIT_POOL, Config.FREE_CREDIT_POOL)
    return pool.free_credits


def get_tool_cost(tool_slug):
    tool = ToolCost.query.filter_by(slug=tool_slug).first()
    if tool is None:
        return Config.TOOL_COSTS.get(tool_slug, 10)
    return tool.credit_cost


def deduct_credits(tool_slug, ip_address=None, user=None):
    if ip_address is None:
        ip_address = get_client_ip()

    if user and user.is_paid:
        log_credit(ip_address, 'bypass_paid', tool_slug, 0, -1, user.id)
        return True

    cost = get_tool_cost(tool_slug)
    pool = IPPool.query.filter_by(ip_address=ip_address).first()
    if pool is None:
        pool = IPPool(ip_address=ip_address, free_credits=Config.FREE_CREDIT_POOL)
        db.session.add(pool)
        db.session.commit()
        log_credit(ip_address, 'pool_created', tool_slug, Config.FREE_CREDIT_POOL, Config.FREE_CREDIT_POOL)

    if pool.free_credits < cost:
        log_credit(ip_address, 'insufficient_credits', tool_slug, cost, pool.free_credits)
        return False

    before = pool.free_credits
    pool.deduct(cost)
    log_entry = UsageLog(
        ip_address=ip_address,
        tool_slug=tool_slug,
        credits_spent=cost,
        user_id=user.id if user else None
    )
    db.session.add(log_entry)
    db.session.commit()

    log_credit(ip_address, 'deduct', tool_slug, cost, pool.free_credits, user.id if user else None)
    return True


def require_credits(tool_slug):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            ip = get_client_ip()
            user = None
            user_id = session.get('user_id')
            if user_id:
                user = User.query.get(user_id)

            has_credits = deduct_credits(tool_slug, ip, user)
            if not has_credits:
                remaining = get_free_credits(ip)
                log_error(f'Insufficient credits for {tool_slug}', ip=ip, tool=tool_slug, remaining=remaining)
                return jsonify({
                    'error': 'insufficient_credits',
                    'message': 'You have run out of free credits. Please purchase more or wait for reset.',
                    'credits_remaining': remaining
                }), 402
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def get_remaining_all_tools(ip_address=None):
    if ip_address is None:
        ip_address = get_client_ip()
    pool = IPPool.query.filter_by(ip_address=ip_address).first()
    if pool is None:
        return Config.FREE_CREDIT_POOL
    return pool.free_credits
