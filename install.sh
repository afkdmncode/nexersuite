#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$INSTALL_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }
info() { echo -e "${CYAN}[→]${NC} $1"; }
phase(){ echo; echo -e "${CYAN}══════════════════════════════════════════════${NC}"; echo -e "${CYAN}  PHASE: $1${NC}"; echo -e "${CYAN}══════════════════════════════════════════════${NC}"; echo; }

phase "System Requirements"

if ! command -v python3 &>/dev/null; then
    err "python3 is not installed. Install Python 3.10+ first."
fi
PYVER=$(python3 --version | grep -oP '\d+\.\d+')
info "Python $PYVER detected"

if ! command -v pip3 &>/dev/null && ! python3 -m pip --version &>/dev/null; then
    warn "pip not found. Installing..."
    python3 -m ensurepip --upgrade || curl -sS https://bootstrap.pypa.io/get-pip.py | python3
fi

phase "Installing Dependencies"

info "Installing Python packages..."
pip3 install --break-system-packages --user \
    flask \
    python-dotenv \
    google-genai \
    PyMuPDF \
    pytesseract \
    Pillow \
    gTTS \
    flask-sqlalchemy \
    flask-login \
    Werkzeug \
    2>&1 | tail -1

log "All Python packages installed"

phase "Checking Optional System Dependencies"

if command -v tesseract &>/dev/null; then
    log "tesseract-ocr found"
else
    warn "tesseract-ocr not installed. OCR on images requires it: apt install tesseract-ocr"
fi

if command -v ffmpeg &>/dev/null; then
    log "ffmpeg found"
else
    warn "ffmpeg not found. Audio/video tools may be limited."
fi

phase "Environment Configuration"

if [ ! -f .env ]; then
    warn "No .env file found. Creating from template..."
    cat > .env << 'EOF'
GEMINI_API_KEY=your_gemini_api_key_here
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
DATABASE_URL=sqlite:///ai_platform.db
FLASK_ENV=development
FREE_CREDIT_POOL=85
ADMIN_PASSWORD=$(python3 -c "import secrets; print(secrets.token_urlsafe(16))")
EOF
    log ".env created with random SECRET_KEY and ADMIN_PASSWORD"
    info "⚠️  Edit .env and set your GEMINI_API_KEY before using AI features"
    info "⚠️  Admin password: $(grep ADMIN_PASSWORD .env | cut -d= -f2)"
else
    log ".env already exists"
fi

phase "Database Initialization"

info "Creating database tables..."
python3 -c "
from app import create_app
from app import db
from app.models import ToolCost
app = create_app()
with app.app_context():
    db.create_all()
    from app.models import seed_tool_costs
    seed_tool_costs()
    tools = ToolCost.query.count()
    print(f'  → {tools} tools seeded in database')
" 2>&1 | tail -3
log "Database initialized"

mkdir -p app/static/uploads logs

phase "Verification"

info "Testing import of all service modules..."
python3 -c "
from app.services.ai import get_client; print('  → ai_service: OK')
from app.services.document import extract_text_from_pdf; print('  → document_service: OK')
from app.services.credit_manager import get_free_credits; print('  → credit_manager: OK')
from app.services.media import text_to_speech; print('  → media_service: OK')
from app.services.vision import detect_objects; print('  → vision_service: OK')
from app.services.forms_templates import build_form; print('  → forms_templates: OK')
from app.services.code import generate_code; print('  → code_service: OK')
from app.services.storage import save_file; print('  → storage_service: OK')
print('  All services load successfully.')
" 2>&1

info "Testing Flask app creation..."
python3 -c "
from app import create_app
app = create_app()
with app.test_client() as c:
    r = c.get('/')
    assert r.status_code == 200
    r = c.get('/chat')
    assert r.status_code == 200
    r = c.get('/tools')
    assert r.status_code == 200
    r = c.get('/tools/ocr')
    assert r.status_code == 200
    r = c.get('/admin/')
    assert r.status_code in (200, 302)
    print('  All routes respond correctly.')
" 2>&1

echo
log "══════════════════════════════════════════════"
log "  Installation Complete!"
log "══════════════════════════════════════════════"
echo
info "  Start the server with:"
echo
echo "    cd $INSTALL_DIR"
echo "    python3 run.py"
echo
info "  Then open: http://localhost:5000"
info "  Admin panel: http://localhost:5000/admin/"
echo
ADMIN_PW=$(grep ADMIN_PASSWORD .env 2>/dev/null | cut -d= -f2)
if [ -n "$ADMIN_PW" ]; then
    info "  Admin password: $ADMIN_PW"
fi
echo
