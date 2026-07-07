from google import genai
from google.genai import types
import io
from app.config import Config

_client = None


def get_client():
    global _client
    if _client is None:
        _client = genai.Client(api_key=Config.GEMINI_API_KEY)
    return _client


def get_model(model_name=None):
    if model_name is None:
        model_name = Config.GEMINI_MODEL
    return model_name


def chat_completion(messages, system_prompt=None):
    client = get_client()
    model = get_model()

    contents = []
    if system_prompt:
        contents.append(system_prompt)

    for msg in messages:
        role = 'user' if msg['role'] == 'user' else 'model'
        contents.append({'role': role, 'parts': [msg['content']]})

    response = client.models.generate_content(
        model=model,
        contents=contents
    )
    return response.text


def chat_stream(messages, system_prompt=None):
    client = get_client()
    model = get_model()

    contents = []
    if system_prompt:
        contents.append(system_prompt)

    for msg in messages:
        role = 'user' if msg['role'] == 'user' else 'model'
        contents.append({'role': role, 'parts': [msg['content']]})

    response = client.models.generate_content_stream(
        model=model,
        contents=contents
    )
    for chunk in response:
        if chunk.text:
            yield chunk.text


def generate_image(prompt):
    client = get_client()
    response = client.models.generate_content(
        model='gemini-2.0-flash-exp',
        contents=[f"Generate an image: {prompt}"]
    )
    return response


def analyze_image(image_bytes, prompt):
    import PIL.Image
    img = PIL.Image.open(io.BytesIO(image_bytes))
    client = get_client()
    response = client.models.generate_content(
        model=get_model(),
        contents=[prompt, img]
    )
    return response.text


def translate_text(text, target_language):
    client = get_client()
    response = client.models.generate_content(
        model=get_model(),
        contents=[f"Translate the following text to {target_language}. Return only the translation:\n\n{text}"]
    )
    return response.text.strip()


def summarize_text(text):
    client = get_client()
    response = client.models.generate_content(
        model=get_model(),
        contents=[f"Summarize the following text concisely:\n\n{text}"]
    )
    return response.text.strip()
