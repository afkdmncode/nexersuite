import json
import time
from flask import Blueprint, render_template, request, jsonify, Response, g
from app.services.ai import chat_stream, chat_completion
from app.services.credit_manager import require_credits, deduct_credits, get_free_credits, get_client_ip
from app.services.logger import log_tool_usage, log_error
from app.models import ToolCost

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/')
def index():
    costs = ToolCost.query.filter_by(is_active=True).order_by(ToolCost.category).all()
    return render_template('chat.html', tools=costs)


@chat_bp.route('/send', methods=['POST'])
@require_credits('chat')
def send():
    start = time.time()
    ip = get_client_ip()
    data = request.get_json()
    messages = data.get('messages', [])
    system = data.get('system', None)
    stream = data.get('stream', False)

    if stream:
        def generate():
            for chunk in chat_stream(messages, system):
                yield f'data: {json.dumps({"text": chunk})}\n\n'
            yield 'data: [DONE]\n\n'
            duration = int((time.time() - start) * 1000)
            log_tool_usage('chat', ip, 'success_stream', duration, 5, msg_count=len(messages))
        return Response(generate(), mimetype='text/event-stream')

    try:
        response = chat_completion(messages, system)
        duration = int((time.time() - start) * 1000)
        log_tool_usage('chat', ip, 'success', duration, 5, msg_count=len(messages), resp_len=len(response))
        credits = get_free_credits()
        return jsonify({
            'response': response,
            'credits_remaining': credits
        })
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        log_error(f'Chat failed: {str(e)}', ip=ip)
        log_tool_usage('chat', ip, 'error', duration, 5)
        return jsonify({'error': str(e)}), 500
