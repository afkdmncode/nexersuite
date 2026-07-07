import os
import fitz
from PIL import Image
import pytesseract
import io


def extract_text_from_pdf(file_bytes, file_ext='pdf'):
    if file_ext.lower() == 'pdf':
        doc = fitz.open(stream=file_bytes, filetype='pdf')
        text = ''
        for page in doc:
            text += page.get_text()
        doc.close()
        return text or None

    elif file_ext.lower() in ('png', 'jpg', 'jpeg', 'tiff', 'bmp'):
        img = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(img)
        return text.strip() or None

    else:
        try:
            doc = fitz.open(stream=file_bytes, filetype='pdf')
            text = ''
            for page in doc:
                text += page.get_text()
            doc.close()
            return text or None
        except Exception:
            img = Image.open(io.BytesIO(file_bytes))
            text = pytesseract.image_to_string(img)
            return text.strip() or None


def extract_text_from_image(file_bytes):
    img = Image.open(io.BytesIO(file_bytes))
    text = pytesseract.image_to_string(img)
    return text.strip()


def convert_to_pdf(file_bytes, output_format='pdf'):
    pass


def add_signature_to_pdf(pdf_bytes, signature_bytes, page_number=0):
    pass
