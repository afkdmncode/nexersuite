import os
import io
import json
import time
from datetime import datetime
from flask import Blueprint, render_template, request, jsonify, current_app, g, send_file
from werkzeug.utils import secure_filename
from app.services.document import extract_text_from_pdf, convert_document, add_signature_to_pdf, create_signature_page
from app.services.ai import generate_image, analyze_image, translate_text, summarize_text, chat_completion
from app.services.media import text_to_speech, transcribe_audio, translate_audio, transcribe_video
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


@tools_bp.route('/transcribe')
def transcribe_page():
    return render_template('tools/transcribe.html')

@tools_bp.route('/convert')
def convert_page():
    return render_template('tools/convert.html')

@tools_bp.route('/translate')
def translate_page():
    return render_template('tools/translate.html')

@tools_bp.route('/sign')
def sign_page():
    return render_template('tools/sign.html')

@tools_bp.route('/detect')
def detect_page():
    return render_template('tools/detect.html')

@tools_bp.route('/segment')
def segment_page():
    return render_template('tools/segment.html')

@tools_bp.route('/pose')
def pose_page():
    return render_template('tools/pose.html')

@tools_bp.route('/code_gen')
def codegen_page():
    return render_template('tools/code_gen.html')

@tools_bp.route('/code_exec')
def codeexec_page():
    return render_template('tools/code_exec.html')

@tools_bp.route('/form_build')
def formbuild_page():
    return render_template('tools/form_build.html')

@tools_bp.route('/resume_build')
def resumebuild_page():
    return render_template('tools/resume_build.html')

@tools_bp.route('/video_transcribe')
def video_transcribe_page():
    return render_template('tools/video_transcribe.html')

@tools_bp.route('/video_analyze')
def video_analyze_page():
    return render_template('tools/video_analyze.html')

@tools_bp.route('/audio_translate')
def audio_translate_page():
    return render_template('tools/audio_translate.html')


@tools_bp.route('/<tool_name>')
def tool_stub(tool_name):
    tool = ToolCost.query.filter_by(slug=tool_name).first()
    if tool is None:
        return render_template('tools/coming_soon.html', tool_name=tool_name)
    return render_template('tools/coming_soon.html', tool=tool)


@tools_bp.route('/document/convert', methods=['GET', 'POST'])
def document_convert():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('document-convert'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 8 credits'}), 402

        target_format = request.form.get('format', 'pdf')
        ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        file_bytes = file.read()

        try:
            result = convert_document(file_bytes, ext, target_format)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('document-convert', ip, 'success', duration, 8,
                           source=ext, target=target_format, filename=file.filename)
            return send_file(
                io.BytesIO(result),
                mimetype='application/pdf' if target_format == 'pdf' else 'text/plain',
                as_attachment=True,
                download_name=f'converted.{target_format}'
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Document convert failed: {str(e)}', ip=ip, filename=file.filename)
            log_tool_usage('document-convert', ip, 'error', duration, 8)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/convert.html')


@tools_bp.route('/document/translate', methods=['GET', 'POST'])
def document_translate():
    if request.method == 'POST':
        start = time.time()
        data = request.get_json()
        text = data.get('text', '')
        target = data.get('target_language', 'English')
        ip = get_client_ip()

        if not text:
            return jsonify({'error': 'No text provided'}), 400

        if not deduct_credits('document-translate'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 10 credits'}), 402

        try:
            result = translate_text(text, target)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('document-translate', ip, 'success', duration, 10,
                           target=target, chars=len(text))
            credits = get_free_credits()
            return jsonify({'translation': result, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Document translate failed: {str(e)}', ip=ip)
            log_tool_usage('document-translate', ip, 'error', duration, 10)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/translate.html')


@tools_bp.route('/document/sign', methods=['GET', 'POST'])
def document_sign():
    if request.method == 'POST':
        start = time.time()
        ip = get_client_ip()

        if not deduct_credits('document-sign'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 12 credits'}), 402

        text = request.form.get('text', '')
        signer_name = request.form.get('signer_name', '')
        date = request.form.get('date', datetime.utcnow().strftime('%Y-%m-%d'))

        try:
            pdf_bytes = create_signature_page(text, signer_name, date)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('document-sign', ip, 'success', duration, 12, signer=signer_name)
            return send_file(
                io.BytesIO(pdf_bytes),
                mimetype='application/pdf',
                as_attachment=True,
                download_name='signed_document.pdf'
            )
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Document sign failed: {str(e)}', ip=ip)
            log_tool_usage('document-sign', ip, 'error', duration, 12)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/sign.html')


@tools_bp.route('/audio/transcribe', methods=['GET', 'POST'])
def audio_transcribe():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('transcribe'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 10 credits'}), 402

        file_bytes = file.read()
        try:
            text = transcribe_audio(file_bytes)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('transcribe', ip, 'success', duration, 10, filename=file.filename)
            credits = get_free_credits()
            return jsonify({'text': text, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Audio transcribe failed: {str(e)}', ip=ip, filename=file.filename)
            log_tool_usage('transcribe', ip, 'error', duration, 10)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/transcribe.html')


@tools_bp.route('/audio/translate', methods=['GET', 'POST'])
def audio_translate():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('chat'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need credits'}), 402

        target = request.form.get('target_language', 'en')
        file_bytes = file.read()
        try:
            text = translate_audio(file_bytes, target)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('audio-translate', ip, 'success', duration, 5, filename=file.filename, target=target)
            credits = get_free_credits()
            return jsonify({'text': text, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Audio translate failed: {str(e)}', ip=ip, filename=file.filename)
            log_tool_usage('audio-translate', ip, 'error', duration, 5)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/audio_translate.html')


@tools_bp.route('/video/transcribe', methods=['GET', 'POST'])
def video_transcribe():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('video-transcribe'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 20 credits'}), 402

        file_bytes = file.read()
        try:
            text = transcribe_video(file_bytes)
            duration = int((time.time() - start) * 1000)
            log_tool_usage('video-transcribe', ip, 'success', duration, 20, filename=file.filename)
            credits = get_free_credits()
            return jsonify({'text': text, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Video transcribe failed: {str(e)}', ip=ip, filename=file.filename)
            log_tool_usage('video-transcribe', ip, 'error', duration, 20)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/video_transcribe.html')


@tools_bp.route('/video/analyze', methods=['GET', 'POST'])
def video_analyze():
    if request.method == 'POST':
        start = time.time()
        ip = get_client_ip()
        data = request.get_json()
        video_url = data.get('url', '')
        question = data.get('question', 'Analyze this video content')

        if not video_url:
            return jsonify({'error': 'No video URL provided'}), 400

        if not deduct_credits('video-analyze'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 25 credits'}), 402

        try:
            prompt = f'Based on the video at {video_url}, answer: {question}'
            from app.services.ai import chat_completion
            response = chat_completion([{'role': 'user', 'content': prompt}])
            duration = int((time.time() - start) * 1000)
            log_tool_usage('video-analyze', ip, 'success', duration, 25, url=video_url[:50])
            credits = get_free_credits()
            return jsonify({'analysis': response, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Video analyze failed: {str(e)}', ip=ip)
            log_tool_usage('video-analyze', ip, 'error', duration, 25)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/video_analyze.html')


@tools_bp.route('/image/detect', methods=['GET', 'POST'])
def image_detect():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('detect'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 15 credits'}), 402

        file_bytes = file.read()
        try:
            result = analyze_image(file_bytes, 'List all objects you can see in this image. Be specific.')
            duration = int((time.time() - start) * 1000)
            log_tool_usage('detect', ip, 'success', duration, 15, filename=file.filename)
            credits = get_free_credits()
            return jsonify({'objects': result, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Object detection failed: {str(e)}', ip=ip, filename=file.filename)
            log_tool_usage('detect', ip, 'error', duration, 15)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/detect.html')


@tools_bp.route('/image/segment', methods=['GET', 'POST'])
def image_segment():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('segment'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 20 credits'}), 402

        file_bytes = file.read()
        try:
            result = analyze_image(file_bytes, 'Describe the different regions/segments of this image. What objects or areas can be identified separately?')
            duration = int((time.time() - start) * 1000)
            log_tool_usage('segment', ip, 'success', duration, 20, filename=file.filename)
            credits = get_free_credits()
            return jsonify({'segments': result, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Image segmentation failed: {str(e)}', ip=ip, filename=file.filename)
            log_tool_usage('segment', ip, 'error', duration, 20)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/segment.html')


@tools_bp.route('/image/pose', methods=['GET', 'POST'])
def image_pose():
    if request.method == 'POST':
        start = time.time()
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        ip = get_client_ip()
        if not deduct_credits('pose'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 10 credits'}), 402

        file_bytes = file.read()
        try:
            result = analyze_image(file_bytes, 'Describe the human poses, positions, and body language visible in this image.')
            duration = int((time.time() - start) * 1000)
            log_tool_usage('pose', ip, 'success', duration, 10, filename=file.filename)
            credits = get_free_credits()
            return jsonify({'poses': result, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Pose detection failed: {str(e)}', ip=ip, filename=file.filename)
            log_tool_usage('pose', ip, 'error', duration, 10)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/pose.html')


@tools_bp.route('/code/generate', methods=['GET', 'POST'])
def code_generate():
    if request.method == 'POST':
        start = time.time()
        data = request.get_json()
        prompt = data.get('prompt', '')
        language = data.get('language', 'python')
        ip = get_client_ip()

        if not prompt:
            return jsonify({'error': 'No prompt provided'}), 400

        if not deduct_credits('code-gen'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 10 credits'}), 402

        try:
            full_prompt = f'Generate {language} code for: {prompt}\nReturn only the code, no explanation.'
            response = chat_completion([{'role': 'user', 'content': full_prompt}])
            duration = int((time.time() - start) * 1000)
            log_tool_usage('code-gen', ip, 'success', duration, 10, lang=language)
            credits = get_free_credits()
            return jsonify({'code': response, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Code generation failed: {str(e)}', ip=ip)
            log_tool_usage('code-gen', ip, 'error', duration, 10)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/code_gen.html')


@tools_bp.route('/code/execute', methods=['GET', 'POST'])
def code_execute():
    if request.method == 'POST':
        start = time.time()
        data = request.get_json()
        code = data.get('code', '')
        language = data.get('language', 'python')
        ip = get_client_ip()

        if not code:
            return jsonify({'error': 'No code provided'}), 400

        if not deduct_credits('code-exec'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 15 credits'}), 402

        try:
            import tempfile, subprocess, os
            with tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w') as f:
                f.write(code)
                f.flush()
                result = subprocess.run(['python3', f.name], capture_output=True, text=True, timeout=15)
                os.unlink(f.name)

            output = result.stdout or result.stderr or '(no output)'
            duration = int((time.time() - start) * 1000)
            log_tool_usage('code-exec', ip, 'success', duration, 15, lang=language)
            credits = get_free_credits()
            return jsonify({'output': output.strip()[:5000], 'credits_remaining': credits})
        except subprocess.TimeoutExpired:
            return jsonify({'error': 'Execution timed out (15s limit)'}), 500
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Code execution failed: {str(e)}', ip=ip)
            log_tool_usage('code-exec', ip, 'error', duration, 15)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/code_exec.html')


@tools_bp.route('/forms/build', methods=['GET', 'POST'])
def forms_build():
    if request.method == 'POST':
        start = time.time()
        data = request.get_json()
        form_title = data.get('title', 'Untitled Form')
        fields = data.get('fields', [])
        ip = get_client_ip()

        if not fields:
            return jsonify({'error': 'No form fields provided'}), 400

        if not deduct_credits('form-build'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 12 credits'}), 402

        try:
            prompt = f'Generate a complete HTML form for "{form_title}" with these fields: {json.dumps(fields)}. Return only the HTML.'
            from app.services.ai import chat_completion
            html = chat_completion([{'role': 'user', 'content': prompt}])
            duration = int((time.time() - start) * 1000)
            log_tool_usage('form-build', ip, 'success', duration, 12)
            credits = get_free_credits()
            return jsonify({'html': html, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Form builder failed: {str(e)}', ip=ip)
            log_tool_usage('form-build', ip, 'error', duration, 12)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/form_build.html')


@tools_bp.route('/forms/resume', methods=['GET', 'POST'])
def forms_resume():
    if request.method == 'POST':
        start = time.time()
        data = request.get_json()
        job_title = data.get('job_title', '')
        skills = data.get('skills', '')
        experience = data.get('experience', '')
        ip = get_client_ip()

        if not job_title:
            return jsonify({'error': 'Job title is required'}), 400

        if not deduct_credits('resume-build'):
            return jsonify({'error': 'insufficient_credits', 'message': 'Need 8 credits'}), 402

        try:
            prompt = f'Create a professional resume for a {job_title} position. Skills: {skills}. Experience: {experience}. Format as clean markdown.'
            from app.services.ai import chat_completion
            resume = chat_completion([{'role': 'user', 'content': prompt}])
            duration = int((time.time() - start) * 1000)
            log_tool_usage('resume-build', ip, 'success', duration, 8, job=job_title)
            credits = get_free_credits()
            return jsonify({'resume': resume, 'credits_remaining': credits})
        except Exception as e:
            duration = int((time.time() - start) * 1000)
            log_error(f'Resume builder failed: {str(e)}', ip=ip)
            log_tool_usage('resume-build', ip, 'error', duration, 8)
            return jsonify({'error': str(e)}), 500

    return render_template('tools/resume_build.html')
