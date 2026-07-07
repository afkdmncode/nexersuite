import time
from flask import Blueprint, render_template, request, jsonify
from app.services.ai import chat_completion, generate_image, translate_text, summarize_text
from app.services.document import extract_text_from_pdf
from app.services.credit_manager import deduct_credits, get_client_ip, get_free_credits
from app.services.logger import log_tool_usage, log_error
from app.models import User, ToolCost

api_bp = Blueprint('api', __name__)


@api_bp.route('/')
def docs():
    tools = ToolCost.query.filter_by(is_active=True).order_by(ToolCost.category).all()
    return render_template('api/docs.html', tools=tools)


def verify_api_key():
    api_key = request.headers.get('X-API-Key') or request.args.get('api_key')
    if not api_key:
        return None
    return User.query.filter_by(api_key=api_key).first()


@api_bp.route('/chat', methods=['POST'])
def api_chat():
    start = time.time()
    user = verify_api_key()
    data = request.get_json()
    messages = data.get('messages', [])
    system = data.get('system', None)
    ip = get_client_ip()

    if not user or not user.is_paid:
        if not deduct_credits('chat', ip, user):
            log_tool_usage('api-chat', ip, 'insufficient_credits', int((time.time()-start)*1000), 5)
            return jsonify({'error': 'insufficient_credits'}), 402

    try:
        response = chat_completion(messages, system)
        duration = int((time.time() - start) * 1000)
        log_tool_usage('api-chat', ip, 'success', duration, 5, api_key=bool(user))
        return jsonify({'response': response, 'credits_remaining': get_free_credits(ip) if not user else -1})
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        log_error(f'API chat failed: {str(e)}', ip=ip)
        log_tool_usage('api-chat', ip, 'error', duration, 5)
        return jsonify({'error': str(e)}), 500


@api_bp.route('/ocr', methods=['POST'])
def api_ocr():
    start = time.time()
    user = verify_api_key()
    ip = get_client_ip()

    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400

    if not user or not user.is_paid:
        if not deduct_credits('ocr', ip, user):
            log_tool_usage('api-ocr', ip, 'insufficient_credits', int((time.time()-start)*1000), 10)
            return jsonify({'error': 'insufficient_credits'}), 402

    try:
        file = request.files['file']
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        text = extract_text_from_pdf(file.read(), ext)
        duration = int((time.time() - start) * 1000)
        log_tool_usage('api-ocr', ip, 'success', duration, 10, filename=file.filename)
        return jsonify({'text': text, 'credits_remaining': get_free_credits(ip) if not user else -1})
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        log_error(f'API OCR failed: {str(e)}', ip=ip)
        log_tool_usage('api-ocr', ip, 'error', duration, 10)
        return jsonify({'error': str(e)}), 500


@api_bp.route('/generate', methods=['POST'])
def api_generate():
    start = time.time()
    user = verify_api_key()
    data = request.get_json()
    prompt = data.get('prompt', '')
    ip = get_client_ip()

    if not prompt:
        return jsonify({'error': 'No prompt provided'}), 400

    if not user or not user.is_paid:
        if not deduct_credits('image-gen', ip, user):
            log_tool_usage('api-generate', ip, 'insufficient_credits', int((time.time()-start)*1000), 20)
            return jsonify({'error': 'insufficient_credits'}), 402

    try:
        result = generate_image(prompt)
        duration = int((time.time() - start) * 1000)
        log_tool_usage('api-generate', ip, 'success', duration, 20, prompt=prompt[:50])
        return jsonify({
            'response': result.text if hasattr(result, 'text') else str(result),
            'credits_remaining': get_free_credits(ip) if not user else -1
        })
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        log_error(f'API generate failed: {str(e)}', ip=ip)
        log_tool_usage('api-generate', ip, 'error', duration, 20)
        return jsonify({'error': str(e)}), 500


@api_bp.route('/translate', methods=['POST'])
def api_translate():
    start = time.time()
    user = verify_api_key()
    data = request.get_json()
    text = data.get('text', '')
    target = data.get('target_language', 'English')
    ip = get_client_ip()

    if not text:
        return jsonify({'error': 'No text provided'}), 400

    if not user or not user.is_paid:
        if not deduct_credits('chat', ip, user):
            log_tool_usage('api-translate', ip, 'insufficient_credits', int((time.time()-start)*1000), 5)
            return jsonify({'error': 'insufficient_credits'}), 402

    try:
        result = translate_text(text, target)
        duration = int((time.time() - start) * 1000)
        log_tool_usage('api-translate', ip, 'success', duration, 5, target_lang=target, chars=len(text))
        return jsonify({'translation': result, 'credits_remaining': get_free_credits(ip) if not user else -1})
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        log_error(f'API translate failed: {str(e)}', ip=ip)
        log_tool_usage('api-translate', ip, 'error', duration, 5)
        return jsonify({'error': str(e)}), 500


@api_bp.route('/tools', methods=['GET'])
def api_list_tools():
    tools = ToolCost.query.filter_by(is_active=True).all()
    return jsonify([{
        'slug': t.slug,
        'name': t.name,
        'category': t.category,
        'credit_cost': t.credit_cost,
        'description': t.description
    } for t in tools])
