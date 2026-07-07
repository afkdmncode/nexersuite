import os
import time
from flask import Blueprint, render_template, request, jsonify, current_app, g
from werkzeug.utils import secure_filename
from app.services.document import extract_text_from_pdf
from app.services.ai import generate_image, analyze_image
from app.services.media import text_to_speech
from app.services.credit_manager import require_credits, get_free_credits, get_client_ip, deduct_credits
from app.services.logger import log_tool_usage, log_error
from app.models import ToolCost

tools_bp = Blueprint('tools', __name__)


@tools_bp.route('/')
def index():
    categories = {
        'document': [],
        'image': [],
        'audio': [],
        'video': [],
        'development': [],
        'forms': [],
    }
    tools = ToolCost.query.filter_by(is_active=True).order_by(ToolCost.category).all()
    for t in tools:
        if t.category in categories:
            categories[t.category].append(t)
    return render_template('tools/index.html', categories=categories)


@tools_bp.route('/ocr', methods=['GET', 'POST'])
def ocr():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('ocr'):
            log_tool_usage('ocr', ip, 'insufficient_credits', int((time.time()-start)*1000), 10)
            return jsonify({
                'error': 'insufficient_credits',
                'message': 'Not enough free credits. You need 10 credits for OCR.'
            }), 402

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

        file_bytes = file.read()
        try:
            text = extract_text_from_pdf(file_bytes, ext)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('ocr', ip, 'success', duration, 10, filename=filename, chars=len(text or ''))
            credits = get_free_credits()
            return jsonify({
                'text': text,
                'credits_remaining': credits,
                'filename': filename
            })
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'OCR failed: {str(e)}', ip=ip, filename=filename)
            log_tool_usage('ocr', ip, 'error', duration, 10)
            return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

    return render_template('tools/ocr.html')


@tools_bp.route('/image-gen', methods=['GET', 'POST'])
def image_gen():
    if request.method == 'POST':
        start = time.time()
        data = request.get_json()
        prompt = data.get('prompt', '')
        ip = get_client_ip()

        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400

        if not deduct_credits('image-gen'):
            log_tool_usage('image-gen', ip, 'insufficient_credits', int((time.time()-start)*1000), 20)
            return jsonify({
                'error': 'insufficient_credits',
                'message': 'Not enough free credits. You need 20 credits for image generation.'
            }), 402

        try:
            result = generate_image(prompt)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('image-gen', ip, 'success', duration, 20, prompt=prompt[:50])
            credits = get_free_credits()
            return jsonify({
                'prompt': prompt,
                'credits_remaining': credits,
                'response': result.text if hasattr(result, 'text') else str(result)
            })
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Image gen failed: {str(e)}', ip=ip, prompt=prompt[:50])
            log_tool_usage('image-gen', ip, 'error', duration, 20)
            return jsonify({'error': f'Generation failed: {str(e)}'}), 500

    return render_template('tools/image_gen.html')


@tools_bp.route('/tts', methods=['GET', 'POST'])
def tts():
    if request.method == 'POST':
        start = time.time()
        data = request.get_json()
        text = data.get('text', '')
        lang = data.get('lang', 'en')
        ip = get_client_ip()

        if not text:
            return jsonify({'error': 'No text provided'}), 400

        if not deduct_credits('tts'):
            log_tool_usage('tts', ip, 'insufficient_credits', int((time.time()-start)*1000), 3)
            return jsonify({'error': 'insufficient_credits', 'message': 'Not enough credits'}), 402

        try:
            audio_fp = text_to_speech(text, lang)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('tts', ip, 'success', duration, 3, chars=len(text), lang=lang)
            credits = get_free_credits()

            from flask import send_file
            return send_file(
                audio_fp,
                mimetype='audio/mpeg',
                as_attachment=True,
                download_name='output.mp3'
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'TTS failed: {str(e)}', ip=ip)
            log_tool_usage('tts', ip, 'error', duration, 3)
            return jsonify({'error': f'TTS failed: {str(e)}'}), 500

    return render_template('tools/tts.html')


@tools_bp.route('/<tool_name>')
def tool_stub(tool_name):
    tool = ToolCost.query.filter_by(slug=tool_name).first()
    if tool is None:
        return render_template('tools/coming_soon.html', tool_name=tool_name)
    return render_template('tools/coming_soon.html', tool=tool)


@tools_bp.route('/document/convert', methods=['GET'])
def document_convert():
    return render_template('tools/coming_soon.html', tool_name='Document Convert')


@tools_bp.route('/document/translate', methods=['GET'])
def document_translate():
    return render_template('tools/coming_soon.html', tool_name='Document Translate')


@tools_bp.route('/document/sign', methods=['GET'])
def document_sign():
    return render_template('tools/coming_soon.html', tool_name='Digital Signatures')


@tools_bp.route('/audio/transcribe', methods=['GET'])
def audio_transcribe():
    return render_template('tools/coming_soon.html', tool_name='Audio Transcription')


@tools_bp.route('/audio/translate', methods=['GET'])
def audio_translate():
    return render_template('tools/coming_soon.html', tool_name='Audio Translation')


@tools_bp.route('/video/transcribe', methods=['GET'])
def video_transcribe():
    return render_template('tools/coming_soon.html', tool_name='Video Transcription')


@tools_bp.route('/video/analyze', methods=['GET'])
def video_analyze():
    return render_template('tools/coming_soon.html', tool_name='Video Analysis')


@tools_bp.route('/image/detect', methods=['GET'])
def image_detect():
    return render_template('tools/coming_soon.html', tool_name='Object Detection')


@tools_bp.route('/image/segment', methods=['GET'])
def image_segment():
    return render_template('tools/coming_soon.html', tool_name='Image Segmentation')


@tools_bp.route('/image/pose', methods=['GET'])
def image_pose():
    return render_template('tools/coming_soon.html', tool_name='Pose Detection')


@tools_bp.route('/code/generate', methods=['GET'])
def code_generate():
    return render_template('tools/coming_soon.html', tool_name='Code Generation')


@tools_bp.route('/code/execute', methods=['GET'])
def code_execute():
    return render_template('tools/coming_soon.html', tool_name='Code Execution')


@tools_bp.route('/forms/build', methods=['GET'])
def forms_build():
    return render_template('tools/coming_soon.html', tool_name='Form Builder')


@tools_bp.route('/forms/resume', methods=['GET'])
def forms_resume():
    return render_template('tools/coming_soon.html', tool_name='Resume Builder')
