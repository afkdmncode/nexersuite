document.addEventListener('DOMContentLoaded', () => {
    updateNavCredits();
});

async function updateNavCredits() {
    try {
        const res = await fetch('/credits/status');
        const data = await res.json();
        const el = document.getElementById('nav-credits');
        if (el) el.textContent = data.credits_remaining;
    } catch (e) {
        // silent fail
    }
}

function updateCredits(amount) {
    const el = document.getElementById('nav-credits');
    if (el) el.textContent = amount;
    const chatEl = document.getElementById('chat-credits');
    if (chatEl) chatEl.textContent = amount;
}
