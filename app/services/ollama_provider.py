import json
import time
import requests
from datetime import datetime
from app import db
from app.models import OllamaInstance
from app.services.logger import log_error


def get_active_instances():
    return OllamaInstance.query.filter_by(is_active=True).order_by(OllamaInstance.priority).all()


def chat_completion(messages, system_prompt=None, model='llama3.2'):
    instances = get_active_instances()
    if not instances:
        raise RuntimeError('No active Ollama instances configured')

    last_error = None
    for inst in instances:
        try:
            return _call_instance(inst, messages, system_prompt, model)
        except requests.exceptions.RequestException as e:
            inst.fail_count = (inst.fail_count or 0) + 1
            if inst.fail_count >= 3:
                inst.is_active = False
            db.session.commit()
            log_error(f'Ollama instance {inst.name} failed: {e}',
                      instance=inst.name, url=inst.url, fail_count=inst.fail_count)
            last_error = e
            continue

    raise RuntimeError(f'All Ollama instances unavailable: {last_error}')


def chat_stream(messages, system_prompt=None, model='llama3.2'):
    instances = get_active_instances()
    if not instances:
        raise RuntimeError('No active Ollama instances configured')

    last_error = None
    for inst in instances:
        try:
            yield from _stream_instance(inst, messages, system_prompt, model)
            return
        except requests.exceptions.RequestException as e:
            inst.fail_count = (inst.fail_count or 0) + 1
            if inst.fail_count >= 3:
                inst.is_active = False
            db.session.commit()
            log_error(f'Ollama stream instance {inst.name} failed: {e}',
                      instance=inst.name, url=inst.url, fail_count=inst.fail_count)
            last_error = e
            continue

    raise RuntimeError(f'All Ollama instances unavailable: {last_error}')


def _build_payload(messages, system_prompt=None, model='llama3.2', stream=False):
    msgs = []
    if system_prompt:
        msgs.append({'role': 'system', 'content': system_prompt})
    for m in messages:
        msgs.append({'role': m['role'], 'content': m['content']})

    return {
        'model': model,
        'messages': msgs,
        'stream': stream,
        'options': {
            'temperature': 0.7,
            'num_predict': 2048,
        }
    }


def _call_instance(inst, messages, system_prompt, model):
    headers = {'Content-Type': 'application/json'}
    if inst.api_key:
        headers['Authorization'] = f'Bearer {inst.api_key}'

    payload = _build_payload(messages, system_prompt, model, stream=False)
    url = f'{inst.url.rstrip("/")}/v1/chat/completions'

    resp = requests.post(url, headers=headers, json=payload, timeout=60)
    resp.raise_for_status()
    data = resp.json()

    inst.last_check = datetime.utcnow()
    inst.fail_count = 0
    db.session.commit()

    return data['choices'][0]['message']['content']


def _stream_instance(inst, messages, system_prompt, model):
    headers = {'Content-Type': 'application/json'}
    if inst.api_key:
        headers['Authorization'] = f'Bearer {inst.api_key}'

    payload = _build_payload(messages, system_prompt, model, stream=True)
    url = f'{inst.url.rstrip("/")}/v1/chat/completions'

    with requests.post(url, headers=headers, json=payload, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data_str = line[6:]
                    if data_str.strip() == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data['choices'][0].get('delta', {})
                        content = delta.get('content', '')
                        if content:
                            yield content
                    except json.JSONDecodeError:
                        continue

    inst.last_check = datetime.utcnow()
    inst.fail_count = 0
    db.session.commit()


def generate_text(prompt, model='llama3.2'):
    return chat_completion([{'role': 'user', 'content': prompt}], model=model)


def list_available_models(instance_id=None):
    if instance_id:
        inst = db.session.get(OllamaInstance, instance_id)
        if not inst:
            return []
        instances = [inst]
    else:
        instances = get_active_instances()

    all_models = set()
    for inst in instances:
        try:
            url = f'{inst.url.rstrip("/")}/api/tags'
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            for m in data.get('models', []):
                all_models.add(m['name'])
        except Exception:
            continue

    return sorted(all_models)


def test_connection(url, api_key=None):
    try:
        headers = {}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        resp = requests.get(f'{url.rstrip("/")}/api/tags', headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        models = [m['name'] for m in data.get('models', [])]
        return {'success': True, 'models': models, 'count': len(models)}
    except Exception as e:
        return {'success': False, 'error': str(e)}
