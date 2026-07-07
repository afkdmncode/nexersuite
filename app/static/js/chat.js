document.addEventListener('DOMContentLoaded', () => {
    const messages = document.getElementById('chat-messages');
    const input = document.getElementById('chat-input');
    const sendBtn = document.getElementById('send-btn');
    const chatCredits = document.getElementById('chat-credits');

    let msgHistory = [];

    input.addEventListener('input', () => {
        sendBtn.disabled = !input.value.trim();
        autoResize(input);
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (!sendBtn.disabled) sendMessage();
        }
    });

    sendBtn.addEventListener('click', sendMessage);

    function autoResize(el) {
        el.style.height = 'auto';
        el.style.height = Math.min(el.scrollHeight, 200) + 'px';
    }

    async function sendMessage() {
        const text = input.value.trim();
        if (!text) return;

        addMessage(text, 'user');
        input.value = '';
        sendBtn.disabled = true;
        autoResize(input);

        addTypingIndicator();

        const command = parseCommand(text);
        if (command) {
            await handleToolCommand(command);
        } else {
            await handleChatMessage(text);
        }
    }

    function parseCommand(text) {
        const cmdMatch = text.match(/^\/(\w+)\s*(.*)/);
        if (!cmdMatch) return null;
        return { command: cmdMatch[1], args: cmdMatch[2] };
    }

    async function handleToolCommand(cmd) {
        removeTypingIndicator();

        switch (cmd.command) {
            case 'ocr':
                addMessage('To use OCR, please go to the <a href="/tools/ocr" class="text-purple-400 underline">OCR tool page</a> and upload your file.', 'ai');
                break;
            case 'imagine':
            case 'image':
                await callToolAPI('/tools/image-gen', { prompt: cmd.args || 'a beautiful landscape' }, 'image-gen');
                break;
            case 'tts':
                addMessage('To use TTS, please go to the <a href="/tools/tts" class="text-purple-400 underline">TTS tool page</a>.', 'ai');
                break;
            case 'help':
                addMessage(`Available commands:\n- <strong>/imagine &lt;prompt&gt;</strong> — Generate an image\n- <strong>/ocr</strong> — Extract text from documents\n- <strong>/tts &lt;text&gt;</strong> — Convert text to speech\n- <strong>/help</strong> — Show this help`, 'ai');
                break;
            default:
                addMessage(`Unknown command: /${cmd.command}. Type <strong>/help</strong> to see available commands.`, 'ai');
        }
        updateNavCredits();
    }

    async function handleChatMessage(text) {
        msgHistory.push({ role: 'user', content: text });

        try {
            const res = await fetch('/chat/send', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    messages: msgHistory.slice(-10),
                    stream: false
                })
            });

            removeTypingIndicator();

            const data = await res.json();
            if (res.status === 402) {
                addMessage('⚠️ ' + (data.message || 'You have run out of free credits. Please purchase more.'), 'ai');
                return;
            }

            addMessage(data.response, 'ai');
            msgHistory.push({ role: 'assistant', content: data.response });
            if (data.credits_remaining !== undefined) {
                updateCredits(data.credits_remaining);
            }
        } catch (e) {
            removeTypingIndicator();
            addMessage('Sorry, something went wrong. Please try again.', 'ai');
        }
    }

    async function callToolAPI(url, body, costKey) {
        try {
            const res = await fetch(url, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body)
            });
            const data = await res.json();
            if (res.status === 402) {
                addMessage('⚠️ ' + (data.message || 'Insufficient credits.'), 'ai');
                return;
            }
            if (data.error) {
                addMessage('Error: ' + data.error, 'ai');
                return;
            }
            const result = data.response || data.text || 'Done.';
            addMessage(result, 'ai');
            updateCredits(data.credits_remaining);
        } catch (e) {
            addMessage('Error calling tool.', 'ai');
        }
    }

    function addMessage(text, role) {
        const div = document.createElement('div');
        div.className = `flex items-start space-x-3 ${role === 'user' ? 'justify-end' : ''}`;

        if (role === 'ai') {
            div.innerHTML = `
                <div class="w-8 h-8 bg-purple-500 rounded-full flex items-center justify-center text-xs font-bold shrink-0">AI</div>
                <div class="bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3 max-w-lg text-sm text-gray-200">${text}</div>
            `;
        } else {
            div.innerHTML = `
                <div class="bg-purple-900/50 border border-purple-800/50 rounded-2xl rounded-tr-sm px-4 py-3 max-w-lg text-sm text-gray-200">${escapeHtml(text)}</div>
                <div class="w-8 h-8 bg-gray-700 rounded-full flex items-center justify-center text-xs font-bold shrink-0">U</div>
            `;
        }

        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    function addTypingIndicator() {
        const div = document.createElement('div');
        div.id = 'typing-indicator';
        div.className = 'flex items-start space-x-3';
        div.innerHTML = `
            <div class="w-8 h-8 bg-purple-500 rounded-full flex items-center justify-center text-xs font-bold shrink-0">AI</div>
            <div class="bg-gray-800 rounded-2xl rounded-tl-sm px-4 py-3">
                <div class="flex space-x-1">
                    <div class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 0s"></div>
                    <div class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 0.1s"></div>
                    <div class="w-2 h-2 bg-gray-500 rounded-full animate-bounce" style="animation-delay: 0.2s"></div>
                </div>
            </div>
        `;
        messages.appendChild(div);
        messages.scrollTop = messages.scrollHeight;
    }

    function removeTypingIndicator() {
        const el = document.getElementById('typing-indicator');
        if (el) el.remove();
    }

    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
});
