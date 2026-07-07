import os
import json
from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from app import db
from app.models import IPPool, UsageLog, ToolCost, User, Payment, UserInteraction, ApiKey, OllamaInstance, AppConfig
from app.services.credit_manager import get_client_ip, get_global_price_multiplier, get_tool_cost
from app.services.logger import log_admin, get_recent_logs, get_log_stats, log_error
from app.services.ollama_provider import test_connection, list_available_models
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
    admin_pw = os.getenv('ADMIN_PASSWORD') or 'admin'
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
    api_key_count = ApiKey.query.count()
    ollama_count = OllamaInstance.query.count()
    interaction_count = UserInteraction.query.count()

    top_tools = db.session.query(
        UsageLog.tool_slug, db.func.count(UsageLog.id).label('count'),
        db.func.sum(UsageLog.credits_spent).label('total_credits')
    ).group_by(UsageLog.tool_slug).order_by(db.func.count(UsageLog.id).desc()).limit(10).all()

    recent_logs = UsageLog.query.order_by(UsageLog.timestamp.desc()).limit(20).all()

    active_ips_24h = UsageLog.query.filter(
        UsageLog.timestamp >= datetime.utcnow() - timedelta(hours=24)
    ).distinct(UsageLog.ip_address).count()

    active_visitors_24h = UserInteraction.query.filter(
        UserInteraction.timestamp >= datetime.utcnow() - timedelta(hours=24)
    ).distinct(UserInteraction.ip_address).count()

    log_stats = get_log_stats()

    return render_template('admin/dashboard.html',
        total_ips=total_ips, total_usage=total_usage,
        total_requests=total_requests, total_credits_used=total_credits_used,
        total_credits_remaining=total_credits_remaining,
        user_count=user_count, top_tools=top_tools,
        recent_logs=recent_logs, active_ips_24h=active_ips_24h,
        active_visitors_24h=active_visitors_24h,
        log_stats=log_stats, api_key_count=api_key_count,
        ollama_count=ollama_count, interaction_count=interaction_count,
        price_multiplier=get_global_price_multiplier())


# ── Tools Management ──

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
    tool.price_multiplier = float(request.form.get('price_multiplier', tool.price_multiplier))
    tool.description = request.form.get('description', tool.description)
    db.session.commit()

    log_admin('update_tool', request.remote_addr, {
        'tool': tool.slug, 'cost': tool.credit_cost,
        'multiplier': tool.price_multiplier, 'active': tool.is_active
    })
    return jsonify({'success': True, 'tool': tool.slug})


# ── IP Pool Management ──

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


# ── Logs ──

@admin_bp.route('/logs')
@admin_required
def logs():
    log_type = request.args.get('type', 'app')
    lines = request.args.get('lines', 100, type=int)
    log_data = get_recent_logs(log_type, lines)
    return render_template('admin/logs.html',
        log_data=log_data, log_type=log_type,
        log_types=['app', 'requests', 'credits', 'admin', 'tools', 'users', 'errors'])


# ── Usage Logs ──

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


# ── User Interactions ──

@admin_bp.route('/interactions')
@admin_required
def interactions():
    page = request.args.get('page', 1, type=int)
    per_page = 100
    action_filter = request.args.get('action', '')
    ip_filter = request.args.get('ip', '')

    query = UserInteraction.query
    if action_filter:
        query = query.filter(UserInteraction.action_type == action_filter)
    if ip_filter:
        query = query.filter(UserInteraction.ip_address.like(f'%{ip_filter}%'))

    records = query.order_by(UserInteraction.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    action_types = db.session.query(UserInteraction.action_type).distinct().all()
    return render_template('admin/interactions.html',
        records=records, action_types=[a[0] for a in action_types],
        action_filter=action_filter, ip_filter=ip_filter)


# ── API Keys ──

@admin_bp.route('/api-keys')
@admin_required
def api_keys():
    keys = ApiKey.query.order_by(ApiKey.created_at.desc()).all()
    return render_template('admin/api_keys.html', keys=keys)


@admin_bp.route('/api-keys/create', methods=['POST'])
@admin_required
def create_api_key():
    name = request.form.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Name is required'}), 400

    key = ApiKey(
        key=ApiKey.generate_key(),
        name=name,
        is_active=True,
        rate_limit=int(request.form.get('rate_limit', 60)),
    )
    db.session.add(key)
    db.session.commit()

    log_admin('create_api_key', request.remote_addr, {'name': name, 'key': key.key[:12] + '...'})
    return jsonify({'success': True, 'key': key.key, 'id': key.id})


@admin_bp.route('/api-keys/toggle', methods=['POST'])
@admin_required
def toggle_api_key():
    key_id = request.form.get('key_id')
    key = db.session.get(ApiKey, int(key_id))
    if not key:
        return jsonify({'error': 'Key not found'}), 404

    key.is_active = not key.is_active
    db.session.commit()
    log_admin('toggle_api_key', request.remote_addr, {'name': key.name, 'active': key.is_active})
    return jsonify({'success': True, 'is_active': key.is_active})


@admin_bp.route('/api-keys/delete', methods=['POST'])
@admin_required
def delete_api_key():
    key_id = request.form.get('key_id')
    key = db.session.get(ApiKey, int(key_id))
    if not key:
        return jsonify({'error': 'Key not found'}), 404

    db.session.delete(key)
    db.session.commit()
    log_admin('delete_api_key', request.remote_addr, {'name': key.name})
    return jsonify({'success': True})


# ── Pricing ──

@admin_bp.route('/pricing')
@admin_required
def pricing():
    tools = ToolCost.query.order_by(ToolCost.category, ToolCost.name).all()
    global_multiplier = get_global_price_multiplier()
    pool_size = Config.FREE_CREDIT_POOL
    return render_template('admin/pricing.html',
        tools=tools, global_multiplier=global_multiplier, pool_size=pool_size)


@admin_bp.route('/pricing/update-global', methods=['POST'])
@admin_required
def update_global_pricing():
    multiplier = float(request.form.get('multiplier', 1.0))
    pool_size = int(request.form.get('pool_size', Config.FREE_CREDIT_POOL))

    AppConfig.set('price_multiplier', str(multiplier))
    Config.FREE_CREDIT_POOL = pool_size

    log_admin('update_global_pricing', request.remote_addr,
              {'multiplier': multiplier, 'pool_size': pool_size})
    return jsonify({'success': True, 'multiplier': multiplier, 'pool_size': pool_size})


# ── Ollama Management ──

@admin_bp.route('/ollama')
@admin_required
def ollama():
    instances = OllamaInstance.query.order_by(OllamaInstance.priority).all()
    provider = AppConfig.get('ai_provider', 'gemini')
    ollama_model = AppConfig.get('ollama_model', 'llama3.2')
    return render_template('admin/ollama.html',
        instances=instances, provider=provider, ollama_model=ollama_model)


@admin_bp.route('/ollama/create', methods=['POST'])
@admin_required
def create_ollama_instance():
    name = request.form.get('name', '').strip()
    url = request.form.get('url', '').strip()
    if not name or not url:
        return jsonify({'error': 'Name and URL are required'}), 400

    inst = OllamaInstance(
        name=name,
        url=url.rstrip('/'),
        api_key=request.form.get('api_key', '').strip() or None,
        is_active=True,
        priority=int(request.form.get('priority', 0)),
    )
    db.session.add(inst)
    db.session.commit()

    log_admin('create_ollama_instance', request.remote_addr, {'name': name, 'url': url})

    auto_sync = request.form.get('auto_sync', '1') == '1'
    if auto_sync:
        sync_models_for_instance(inst)

    return jsonify({'success': True, 'id': inst.id})


@admin_bp.route('/ollama/test', methods=['POST'])
@admin_required
def test_ollama():
    url = request.form.get('url', '').strip()
    api_key = request.form.get('api_key', '').strip() or None
    result = test_connection(url, api_key)
    return jsonify(result)


@admin_bp.route('/ollama/toggle', methods=['POST'])
@admin_required
def toggle_ollama():
    inst_id = request.form.get('instance_id')
    inst = db.session.get(OllamaInstance, int(inst_id))
    if not inst:
        return jsonify({'error': 'Instance not found'}), 404

    inst.is_active = not inst.is_active
    db.session.commit()
    log_admin('toggle_ollama', request.remote_addr, {'name': inst.name, 'active': inst.is_active})
    return jsonify({'success': True, 'is_active': inst.is_active})


@admin_bp.route('/ollama/delete', methods=['POST'])
@admin_required
def delete_ollama():
    inst_id = request.form.get('instance_id')
    inst = db.session.get(OllamaInstance, int(inst_id))
    if not inst:
        return jsonify({'error': 'Instance not found'}), 404

    db.session.delete(inst)
    db.session.commit()
    log_admin('delete_ollama', request.remote_addr, {'name': inst.name})
    return jsonify({'success': True})


@admin_bp.route('/ollama/set-provider', methods=['POST'])
@admin_required
def set_provider():
    provider = request.form.get('provider', 'gemini')
    AppConfig.set('ai_provider', provider)
    if provider == 'ollama':
        model = request.form.get('ollama_model', 'llama3.2')
        AppConfig.set('ollama_model', model)

    log_admin('set_provider', request.remote_addr, {'provider': provider})
    return jsonify({'success': True, 'provider': provider})


# ── Ollama Model Management ──

def sync_models_for_instance(inst):
    """Pull model list from an Ollama instance and create OllamaModel entries."""
    from app.services.ollama_provider import list_available_models
    model_names = list_available_models(inst.id)
    existing = {m.model_name for m in inst.models.all()}
    added = 0
    for name in model_names:
        if name not in existing:
            db.session.add(OllamaModel(
                instance_id=inst.id,
                model_name=name,
                is_free=True,
                credit_cost=0,
                is_active=True,
            ))
            added += 1
    db.session.commit()
    return added


@admin_bp.route('/ollama/<int:instance_id>/models')
@admin_required
def ollama_models(instance_id):
    inst = db.session.get(OllamaInstance, instance_id)
    if not inst:
        return jsonify({'error': 'Instance not found'}), 404

    models = OllamaModel.query.filter_by(instance_id=instance_id).order_by(OllamaModel.model_name).all()
    return render_template('admin/ollama_models.html', instance=inst, models=models)


@admin_bp.route('/ollama/models/sync', methods=['POST'])
@admin_required
def sync_models():
    instance_id = request.form.get('instance_id')
    inst = db.session.get(OllamaInstance, int(instance_id))
    if not inst:
        return jsonify({'error': 'Instance not found'}), 404

    added = sync_models_for_instance(inst)
    log_admin('sync_ollama_models', request.remote_addr, {'instance': inst.name, 'added': added})
    return jsonify({'success': True, 'added': added, 'total': inst.models.count()})


@admin_bp.route('/ollama/models/update', methods=['POST'])
@admin_required
def update_model():
    model_id = request.form.get('model_id')
    mdl = db.session.get(OllamaModel, int(model_id))
    if not mdl:
        return jsonify({'error': 'Model not found'}), 404

    mdl.is_free = request.form.get('is_free', '1') == '1'
    mdl.credit_cost = int(request.form.get('credit_cost', '0'))
    mdl.requires_paid_account = request.form.get('requires_paid', '0') == '1'
    mdl.is_active = request.form.get('is_active', '1') == '1'
    db.session.commit()

    log_admin('update_ollama_model', request.remote_addr, {
        'model': mdl.model_name, 'free': mdl.is_free,
        'cost': mdl.credit_cost, 'paid_only': mdl.requires_paid_account
    })
    return jsonify({'success': True})


# ── System ──

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
        system_info = {'status': 'psutil not available; install: pip install psutil'}

    return render_template('admin/system.html',
        log_stats=log_stats, db_size_mb=round(db_size / 1024 / 1024, 2),
        system_info=system_info)
