from flask import Blueprint, render_template, jsonify
from app.services.credit_manager import get_free_credits, get_client_ip
from app.models import UsageLog, ToolCost
from app.config import Config

credits_bp = Blueprint('credits', __name__)


@credits_bp.route('/')
def index():
    ip = get_client_ip()
    remaining = get_free_credits(ip)
    total = Config.FREE_CREDIT_POOL
    tools = ToolCost.query.filter_by(is_active=True).order_by(ToolCost.category).all()
    return render_template('credits/index.html',
                           remaining=remaining, total=total, tools=tools)


@credits_bp.route('/status')
def status():
    ip = get_client_ip()
    remaining = get_free_credits(ip)
    recent = UsageLog.query.filter_by(ip_address=ip)\
        .order_by(UsageLog.timestamp.desc())\
        .limit(10)\
        .all()
    return jsonify({
        'ip': ip,
        'credits_remaining': remaining,
        'total_pool': Config.FREE_CREDIT_POOL,
        'recent_usage': [{
            'tool': r.tool_slug,
            'cost': r.credits_spent,
            'time': r.timestamp.isoformat()
        } for r in recent]
    })
