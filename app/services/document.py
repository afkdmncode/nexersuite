import os
import io
import subprocess
import tempfile
import fitz
from PIL import Image
import pytesseract


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


def convert_document(file_bytes, source_ext, target_format='pdf'):
    """Convert between document formats using pandoc or python-docx."""
    source_ext = source_ext.lower().lstrip('.')
    target_format = target_format.lower().lstrip('.')

    try:
        import pypandoc
        with tempfile.NamedTemporaryFile(suffix=f'.{source_ext}', delete=False) as tmp_in:
            tmp_in.write(file_bytes)
            tmp_in_path = tmp_in.name

        tmp_out_path = tempfile.mktemp(suffix=f'.{target_format}')

        extra_args = ['--from', source_ext, '--to', target_format]
        pypandoc.convert_file(tmp_in_path, target_format, outputfile=tmp_out_path,
                              extra_args=['--from', source_ext, '--to', target_format])

        with open(tmp_out_path, 'rb') as f:
            result = f.read()

        os.unlink(tmp_in_path)
        os.unlink(tmp_out_path)
        return result

    except ImportError:
        return _convert_fallback(file_bytes, source_ext, target_format)


def _convert_fallback(file_bytes, source_ext, target_format):
    """Basic fallback conversion without pandoc."""
    if source_ext in ('txt', 'text') and target_format == 'pdf':
        text = file_bytes.decode('utf-8', errors='replace')
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text(fitz.Point(50, 50), text, fontsize=11)
        pdf_bytes = doc.tobytes()
        doc.close()
        return pdf_bytes

    if source_ext == 'pdf' and target_format == 'txt':
        doc = fitz.open(stream=file_bytes, filetype='pdf')
        text = ''
        for page in doc:
            text += page.get_text()
        doc.close()
        return text.encode('utf-8')

    raise ValueError(f'Conversion from {source_ext} to {target_format} not supported without pandoc')


def add_signature_to_pdf(pdf_bytes, signature_bytes, page_number=0, x=100, y=400):
    """Add a signature image to a specific page of a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype='pdf')
    if page_number >= len(doc):
        page_number = len(doc) - 1

    page = doc[page_number]
    sig_image = fitz.Pixmap(signature_bytes)
    rect = fitz.Rect(x, y, x + sig_image.width * 0.5, y + sig_image.height * 0.5)
    page.insert_image(rect, pixmap=sig_image)

    signed_bytes = doc.tobytes()
    doc.close()
    return signed_bytes


def create_signature_page(text, signer_name, date):
    """Create a simple PDF signature page."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(fitz.Point(50, 100), 'DIGITAL SIGNATURE PAGE', fontsize=18)
    page.insert_text(fitz.Point(50, 150), f'Document: {text[:50]}...' if len(text) > 50 else f'Document: {text}', fontsize=11)
    page.insert_text(fitz.Point(50, 200), f'Signed by: {signer_name}', fontsize=11)
    page.insert_text(fitz.Point(50, 250), f'Date: {date}', fontsize=11)
    page.insert_text(fitz.Point(50, 350), 'Digital Signature: [SIGNED]', fontsize=14, color=(0, 0.5, 0))
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes
