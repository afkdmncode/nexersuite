import os
import json
from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from app import db
from app.models import IPPool, UsageLog, ToolCost, User, Payment
from app.services.credit_manager import get_client_ip
from app.services.logger import log_admin, get_recent_logs, get_log_stats, log_error
from app.config import Config

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_authenticated'):
            return redirect(url_for('admin.login'))
        return f(*args, **kwargs)
    return decorated


def verify_admin_password(password):
    admin_pw = os.getenv('ADMIN_PASSWORD') or Config.__dict__.get('ADMIN_PASSWORD', 'admin')
    return password == admin_pw


@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if verify_admin_password(password):
            session['admin_authenticated'] = True
            session['admin_ip'] = get_client_ip()
            log_admin('login', request.remote_addr)
            return redirect(url_for('admin.dashboard'))
        log_admin('failed_login', request.remote_addr)
        return render_template('admin/login.html', error='Invalid password')
    return render_template('admin/login.html')


@admin_bp.route('/logout')
def logout():
    log_admin('logout', request.remote_addr)
    session.pop('admin_authenticated', None)
    return redirect(url_for('admin.login'))


@admin_bp.route('/')
@admin_required
def dashboard():
    total_ips = IPPool.query.count()
    total_usage = db.session.query(db.func.sum(UsageLog.credits_spent)).scalar() or 0
    total_requests = UsageLog.query.count()
    total_credits_used = db.session.query(db.func.sum(IPPool.total_used)).scalar() or 0
    total_credits_remaining = db.session.query(db.func.sum(IPPool.free_credits)).scalar() or 0
    user_count = User.query.count()

    top_tools = db.session.query(
        UsageLog.tool_slug, db.func.count(UsageLog.id).label('count'),
        db.func.sum(UsageLog.credits_spent).label('total_credits')
    ).group_by(UsageLog.tool_slug).order_by(db.func.count(UsageLog.id).desc()).limit(10).all()

    recent_logs = UsageLog.query.order_by(UsageLog.timestamp.desc()).limit(20).all()

    active_ips_24h = UsageLog.query.filter(
        UsageLog.timestamp >= datetime.utcnow() - timedelta(hours=24)
    ).distinct(UsageLog.ip_address).count()

    log_stats = get_log_stats()

    return render_template('admin/dashboard.html',
        total_ips=total_ips, total_usage=total_usage,
        total_requests=total_requests, total_credits_used=total_credits_used,
        total_credits_remaining=total_credits_remaining,
        user_count=user_count, top_tools=top_tools,
        recent_logs=recent_logs, active_ips_24h=active_ips_24h,
        log_stats=log_stats)


@admin_bp.route('/tools')
@admin_required
def tools():
    all_tools = ToolCost.query.order_by(ToolCost.category, ToolCost.name).all()
    return render_template('admin/tools.html', tools=all_tools)


@admin_bp.route('/tools/update', methods=['POST'])
@admin_required
def update_tool():
    tool_id = request.form.get('tool_id')
    tool = db.session.get(ToolCost, int(tool_id))
    if not tool:
        return jsonify({'error': 'Tool not found'}), 404

    tool.credit_cost = int(request.form.get('credit_cost', tool.credit_cost))
    tool.is_active = request.form.get('is_active', '1') == '1'
    tool.is_paid_only = request.form.get('is_paid_only', '0') == '1'
    tool.description = request.form.get('description', tool.description)
    db.session.commit()

    log_admin('update_tool', request.remote_addr, {
        'tool': tool.slug, 'cost': tool.credit_cost,
        'active': tool.is_active
    })
    return jsonify({'success': True, 'tool': tool.slug})


@admin_bp.route('/ips')
@admin_required
def ip_pools():
    page = request.args.get('page', 1, type=int)
    per_page = 50
    pools = IPPool.query.order_by(IPPool.free_credits.asc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template('admin/ips.html', pools=pools)


@admin_bp.route('/ips/reset', methods=['POST'])
@admin_required
def reset_ip():
    ip_id = request.form.get('ip_id')
    pool = db.session.get(IPPool, int(ip_id))
    if not pool:
        return jsonify({'error': 'IP not found'}), 404

    before = pool.free_credits
    pool.free_credits = Config.FREE_CREDIT_POOL
    pool.last_reset = datetime.utcnow()
    db.session.commit()

    log_admin('reset_ip_credits', request.remote_addr, {
        'ip': pool.ip_address, 'before': before, 'after': pool.free_credits
    })
    return jsonify({'success': True, 'ip': pool.ip_address, 'new_credits': pool.free_credits})


@admin_bp.route('/logs')
@admin_required
def logs():
    log_type = request.args.get('type', 'app')
    lines = request.args.get('lines', 100, type=int)
    log_data = get_recent_logs(log_type, lines)
    return render_template('admin/logs.html',
        log_data=log_data, log_type=log_type,
        log_types=['app', 'requests', 'credits', 'admin', 'tools', 'errors'])


@admin_bp.route('/usage')
@admin_required
def usage():
    page = request.args.get('page', 1, type=int)
    per_page = 100
    tool_filter = request.args.get('tool', '')
    ip_filter = request.args.get('ip', '')

    query = UsageLog.query
    if tool_filter:
        query = query.filter(UsageLog.tool_slug == tool_filter)
    if ip_filter:
        query = query.filter(UsageLog.ip_address.like(f'%{ip_filter}%'))

    logs = query.order_by(UsageLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    tools_list = ToolCost.query.filter_by(is_active=True).all()
    return render_template('admin/usage.html',
        logs=logs, tools=tools_list,
        tool_filter=tool_filter, ip_filter=ip_filter)


@admin_bp.route('/system')
@admin_required
def system():
    log_stats = get_log_stats()
    db_size = 0
    db_path = Config.SQLALCHEMY_DATABASE_URI.replace('sqlite:///', '')
    if os.path.exists(db_path):
        db_size = os.path.getsize(db_path)

    try:
        import psutil
        import platform
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        system_info = {
            'platform': platform.platform(),
            'python': platform.python_version(),
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used_mb': memory.used / 1024 / 1024,
            'memory_total_mb': memory.total / 1024 / 1024,
            'disk_percent': disk.percent,
            'disk_free_gb': disk.free / 1024 / 1024 / 1024,
            'disk_total_gb': disk.total / 1024 / 1024 / 1024,
        }
    except Exception:
        system_info = {'status': 'psutil not available; install for system metrics: pip install psutil'}

    return render_template('admin/system.html',
        log_stats=log_stats, db_size_mb=round(db_size / 1024 / 1024, 2),
        system_info=system_info)
