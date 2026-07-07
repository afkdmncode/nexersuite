import io
import time
from google import genai
from app.config import Config
from app.models import AppConfig, OllamaModel, OllamaInstance
from app.services.ollama_provider import (
    chat_completion as ollama_chat,
    chat_stream as ollama_stream,
    generate_text as ollama_generate,
)
from app.services.logger import log_error, app_log

_client = None


# ── Provider Configuration ──

def get_active_provider():
    return AppConfig.get('ai_provider', 'gemini')


def get_fallback_provider():
    return AppConfig.get('fallback_provider', 'gemini' if get_active_provider() == 'ollama' else 'ollama')


def get_ollama_model():
    return AppConfig.get('ollama_model', 'llama3.2')


def provider_can(provider, capability):
    """Check if a provider supports a given capability."""
    capabilities = {
        'gemini': ['chat', 'stream', 'image_gen', 'vision', 'translate', 'summarize'],
        'ollama': ['chat', 'stream', 'translate', 'summarize'],
    }
    return capability in capabilities.get(provider, [])


# ── Gemini Client ──

def get_gemini_client():
    global _client
    if _client is None:
        if not Config.GEMINI_API_KEY or Config.GEMINI_API_KEY == 'your_gemini_api_key_here':
            return None
        _client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _client


def get_gemini_model():
    return AppConfig.get('gemini_model', Config.GEMINI_MODEL)


# ── Ollama Model Lookup ──

def get_ollama_model_cost(model_name):
    """Check if model is free or paid. Returns (is_free, credit_cost, requires_paid)."""
    mdl = OllamaModel.query.filter_by(model_name=model_name, is_active=True).first()
    if mdl:
        return (mdl.is_free, mdl.credit_cost, mdl.requires_paid_account)
    return (True, 0, False)


# ── Provider Call with Failover ──

def _call_with_failover(primary_provider, capability, primary_fn, fallback_fn, *args, **kwargs):
    """Try primary provider, fall back to secondary on failure."""
    if not provider_can(primary_provider, capability):
        app_log.info(f'{primary_provider} cannot {capability}, falling back')
        return fallback_fn(*args, **kwargs)

    start = time.time()
    try:
        result = primary_fn(*args, **kwargs)
        app_log.debug(f'{primary_provider} {capability} OK ({int((time.time()-start)*1000)}ms)')
        return result
    except Exception as e:
        duration = int((time.time() - start) * 1000)
        log_error(f'{primary_provider} {capability} failed after {duration}ms: {e}',
                  provider=primary_provider, capability=capability)

        fallback = get_fallback_provider()
        if fallback and fallback != primary_provider and provider_can(fallback, capability):
            app_log.info(f'Failing over {capability} from {primary_provider} to {fallback}')
            return fallback_fn(*args, **kwargs)

        raise


# ── Chat ──

def chat_completion(messages, system_prompt=None):
    provider = get_active_provider()
    model = get_ollama_model() if provider == 'ollama' else get_gemini_model()

    def _gemini_chat():
        client = get_gemini_client()
        if not client:
            raise RuntimeError('Gemini API key not configured')
        contents = []
        if system_prompt:
            contents.append(system_prompt)
        for msg in messages:
            role = 'user' if msg['role'] == 'user' else 'model'
            contents.append({'role': role, 'parts': [msg['content']]})
        resp = client.models.generate_content(model=get_gemini_model(), contents=contents)
        return resp.text

    def _ollama_chat():
        return ollama_chat(messages, system_prompt, model=model)

    if provider == 'ollama':
        return _call_with_failover('ollama', 'chat', _ollama_chat, _gemini_chat)
    else:
        return _call_with_failover('gemini', 'chat', _gemini_chat, _ollama_chat)


def chat_stream(messages, system_prompt=None):
    provider = get_active_provider()
    model = get_ollama_model() if provider == 'ollama' else get_gemini_model()

    def _gemini_stream():
        client = get_gemini_client()
        if not client:
            raise RuntimeError('Gemini API key not configured')
        contents = []
        if system_prompt:
            contents.append(system_prompt)
        for msg in messages:
            role = 'user' if msg['role'] == 'user' else 'model'
            contents.append({'role': role, 'parts': [msg['content']]})
        resp = client.models.generate_content_stream(model=get_gemini_model(), contents=contents)
        for chunk in resp:
            if chunk.text:
                yield chunk.text

    def _ollama_stream():
        yield from ollama_stream(messages, system_prompt, model=model)

    if provider == 'ollama':
        yield from _call_with_failover('ollama', 'stream', lambda: list(_ollama_stream()), lambda: list(_gemini_stream()))
    else:
        yield from _call_with_failover('gemini', 'stream', lambda: list(_gemini_stream()), lambda: list(_ollama_stream()))


# ── Image Generation (Gemini only, no Ollama fallback) ──

def generate_image(prompt):
    client = get_gemini_client()
    if not client:
        raise RuntimeError('Gemini API key not configured. Image generation requires Gemini.')
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash-exp',
            contents=[f"Generate an image: {prompt}"]
        )
        return response
    except Exception as e:
        log_error(f'Image generation failed: {e}', prompt=prompt[:50])
        raise


# ── Vision (Gemini only) ──

def analyze_image(image_bytes, prompt):
    import PIL.Image
    client = get_gemini_client()
    if not client:
        raise RuntimeError('Gemini API key not configured. Image analysis requires Gemini.')
    img = PIL.Image.open(io.BytesIO(image_bytes))
    response = client.models.generate_content(
        model=get_gemini_model(),
        contents=[prompt, img]
    )
    return response.text


# ── Translation (both providers, with failover) ──

def translate_text(text, target_language):
    def _gemini_translate():
        client = get_gemini_client()
        resp = client.models.generate_content(
            model=get_gemini_model(),
            contents=[f"Translate the following text to {target_language}. Return only the translation:\n\n{text}"]
        )
        return resp.text.strip()

    def _ollama_translate():
        return ollama_chat(
            [{'role': 'user', 'content': f"Translate the following text to {target_language}. Return only the translation:\n\n{text}"}],
            model=get_ollama_model()
        )

    provider = get_active_provider()
    if provider == 'ollama':
        return _call_with_failover('ollama', 'translate', _ollama_translate, _gemini_translate)
    else:
        return _call_with_failover('gemini', 'translate', _gemini_translate, _ollama_translate)


# ── Summarization (both providers, with failover) ──

def summarize_text(text):
    def _gemini_summarize():
        client = get_gemini_client()
        resp = client.models.generate_content(
            model=get_gemini_model(),
            contents=[f"Summarize the following text concisely:\n\n{text}"]
        )
        return resp.text.strip()

    def _ollama_summarize():
        return ollama_chat(
            [{'role': 'user', 'content': f"Summarize the following text concisely:\n\n{text}"}],
            model=get_ollama_model()
        )

    provider = get_active_provider()
    if provider == 'ollama':
        return _call_with_failover('ollama', 'summarize', _ollama_summarize, _gemini_summarize)
    else:
        return _call_with_failover('gemini', 'summarize', _gemini_summarize, _ollama_summarize)
