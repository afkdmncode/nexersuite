document.addEventListener('DOMContentLoaded', () => {
    updateNavCredits();
    setupMobileMenu();
});

// ── Credit Display ──

async function updateNavCredits() {
    try {
        const res = await fetch('/credits/status');
        const data = await res.json();
        const el = document.getElementById('nav-credits');
        if (el) el.textContent = data.credits_remaining;
        updateCreditBar(data.credits_remaining);
    } catch (e) {
        // silent fail
    }
}

function updateCredits(amount) {
    const el = document.getElementById('nav-credits');
    if (el) el.textContent = amount;
    const chatEl = document.getElementById('chat-credits');
    if (chatEl) chatEl.textContent = amount;
    updateCreditBar(amount);
}

function updateCreditBar(amount) {
    const max = 85;
    const pct = Math.min(100, (amount / max) * 100);
    document.querySelectorAll('.credit-bar-fill').forEach(el => {
        el.style.width = pct + '%';
    });
}

// ── Toast Notifications ──

function showToast(message, type) {
    type = type || 'success';
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = {
        success: '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/></svg>',
        error: '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>',
        info: '<svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>'
    };

    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.innerHTML = (icons[type] || icons.info) + message;
    container.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('toast-leaving');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ── Mobile Menu ──

function setupMobileMenu() {
    const btn = document.getElementById('mobile-menu-btn');
    const menu = document.getElementById('mobile-menu');
    if (!btn || !menu) return;

    btn.addEventListener('click', () => {
        const open = menu.classList.toggle('open');
        btn.classList.toggle('open', open);
        menu.classList.toggle('hidden', !open);
    });

    // Close menu on link click
    menu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            menu.classList.remove('open');
            menu.classList.add('hidden');
            btn.classList.remove('open');
        });
    });
}
