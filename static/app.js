/**
 * FramingBot — Frontend Application
 *
 * Chat interaction, real-time structure updates, Notion actions.
 */

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const state = {
    sessionId: null,
    phase: 'greeting',
    framing: {},
    isLoading: false,
};

// ---------------------------------------------------------------------------
// DOM refs
// ---------------------------------------------------------------------------

const $chatMessages = document.getElementById('chatMessages');
const $chatForm = document.getElementById('chatForm');
const $chatInput = document.getElementById('chatInput');
const $sendBtn = document.getElementById('sendBtn');
const $typingIndicator = document.getElementById('typingIndicator');
const $phaseIndicator = document.getElementById('phaseIndicator');

const $btnSaveNotion = document.getElementById('btnSaveNotion');
const $btnSyncNotion = document.getElementById('btnSyncNotion');
const $btnLogicCheck = document.getElementById('btnLogicCheck');

const $syncModal = document.getElementById('syncModal');
const $notionPageIdInput = document.getElementById('notionPageIdInput');
const $syncCancel = document.getElementById('syncCancel');
const $syncConfirm = document.getElementById('syncConfirm');

const $logicCheckResults = document.getElementById('logicCheckResults');
const $logicCheckContent = document.getElementById('logicCheckContent');

// Field ID map
const FIELD_MAP = {
    'Research Type': 'field-ResearchType',
    'Background': 'field-Background',
    'Purpose': 'field-Purpose',
    'RQ': 'field-RQ',
    'Method': 'field-Method',
    'Result': 'field-Result',
    'Contribution': 'field-Contribution',
};

// Phase display names
const PHASE_NAMES = {
    greeting: '👋 開始',
    tension_discovery: '🔍 探索張力',
    positioning: '🎯 建立立場',
    question_sharpening: '❓ 鍛造問題',
    method_contribution: '🛠️ 方法與貢獻',
    complete: '✅ 完成',
};

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function api(endpoint, body = {}) {
    const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        const error = new Error(err.detail || 'API Error');
        error.status = res.status;
        throw error;
    }
    return res.json();
}

async function recreateSession() {
    console.log('Session lost, recreating...');
    const data = await api('/chat/start', { owner: '' });
    state.sessionId = data.session_id;
    updatePhase(data.phase);
    return data.session_id;
}

// ---------------------------------------------------------------------------
// Chat functions
// ---------------------------------------------------------------------------

function addMessage(role, text) {
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role}`;

    const label = document.createElement('span');
    label.className = 'bubble-label';
    label.textContent = role === 'agent' ? 'Agent' : 'You';

    const content = document.createElement('span');
    content.textContent = text;

    bubble.appendChild(label);
    bubble.appendChild(content);
    $chatMessages.appendChild(bubble);

    // Scroll to bottom
    requestAnimationFrame(() => {
        $chatMessages.scrollTop = $chatMessages.scrollHeight;
    });
}

function setLoading(loading) {
    state.isLoading = loading;
    $sendBtn.disabled = loading;
    $chatInput.disabled = loading;
    $typingIndicator.classList.toggle('active', loading);
}

function updatePhase(phase) {
    state.phase = phase;
    const $text = $phaseIndicator.querySelector('.phase-text');
    $text.textContent = PHASE_NAMES[phase] || phase;

    const $dot = $phaseIndicator.querySelector('.phase-dot');
    if (phase === 'complete') {
        $dot.style.background = '#34d399';
    } else {
        $dot.style.background = '#8b5cf6';
    }
}

function updateFraming(framing) {
    state.framing = framing;

    for (const [field, elId] of Object.entries(FIELD_MAP)) {
        const el = document.getElementById(elId);
        const value = framing[field] || '';
        const card = el.closest('.field-card');

        if (value) {
            // Check if this is a new value (for glow animation)
            const prevText = el.textContent;
            if (prevText !== value && !el.querySelector('.field-empty')) {
                // Value changed — trigger glow
                card.classList.remove('just-filled');
                void card.offsetWidth; // force reflow
                card.classList.add('just-filled');
            } else if (el.querySelector('.field-empty')) {
                // First time filled
                card.classList.add('just-filled');
            }

            el.textContent = value;
            card.classList.add('filled');
        }
    }

    // Enable buttons when we have some content
    const hasContent = Object.values(FIELD_MAP).some(elId => {
        const el = document.getElementById(elId);
        return el && !el.querySelector('.field-empty') && el.textContent.trim();
    });

    $btnSaveNotion.disabled = !hasContent;
    $btnSyncNotion.disabled = !state.sessionId;
    $btnLogicCheck.disabled = !framing['RQ'];
}

// ---------------------------------------------------------------------------
// Session start
// ---------------------------------------------------------------------------

async function startSession() {
    try {
        const data = await api('/chat/start', { owner: '' });
        state.sessionId = data.session_id;
        updatePhase(data.phase);
        updateFraming(data.framing);
        addMessage('agent', data.agent_message);
        $btnSyncNotion.disabled = false;
    } catch (err) {
        addMessage('agent', '⚠️ 無法啟動對話，請確認伺服器是否正在運行。');
        console.error(err);
    }
}

// ---------------------------------------------------------------------------
// Send message
// ---------------------------------------------------------------------------

async function sendMessage(text) {
    if (!text.trim() || state.isLoading) return;

    addMessage('user', text);
    $chatInput.value = '';
    $chatInput.style.height = 'auto';
    setLoading(true);

    try {
        let data;
        try {
            data = await api('/chat/message', {
                session_id: state.sessionId,
                message: text,
            });
        } catch (err) {
            // Session lost (404) — recreate and retry
            if (err.status === 404 || (err.message && err.message.includes('not found'))) {
                await recreateSession();
                data = await api('/chat/message', {
                    session_id: state.sessionId,
                    message: text,
                });
            } else {
                throw err;
            }
        }

        addMessage('agent', data.agent_message);
        updatePhase(data.phase);
        updateFraming(data.framing);

        if (data.extraction_happened) {
            const panel = document.querySelector('.structure-panel');
            panel.style.borderLeft = '2px solid rgba(139, 92, 246, 0.5)';
            setTimeout(() => { panel.style.borderLeft = 'none'; }, 1500);
        }
    } catch (err) {
        addMessage('agent', `⚠️ 發生錯誤：${err.message}`);
        console.error(err);
    } finally {
        setLoading(false);
        $chatInput.focus();
    }
}

// ---------------------------------------------------------------------------
// Notion actions
// ---------------------------------------------------------------------------

async function saveToNotion() {
    if (!state.sessionId) return;
    $btnSaveNotion.disabled = true;
    $btnSaveNotion.querySelector('.btn-icon').textContent = '⏳';

    try {
        const data = await api('/chat/save-notion', {
            session_id: state.sessionId,
        });
        $btnSaveNotion.querySelector('.btn-icon').textContent = '✅';
        addMessage('agent', `📤 已儲存到 Notion！\n🔗 Page ID: ${data.page_id}`);
        if (data.url) {
            addMessage('agent', `🔗 ${data.url}`);
        }
    } catch (err) {
        $btnSaveNotion.querySelector('.btn-icon').textContent = '📤';
        addMessage('agent', `⚠️ 儲存失敗：${err.message}`);
    } finally {
        $btnSaveNotion.disabled = false;
    }
}

async function syncFromNotion(pageId) {
    if (!state.sessionId || !pageId) return;
    $btnSyncNotion.disabled = true;

    try {
        const data = await api('/notion-sync', {
            session_id: state.sessionId,
            notion_page_id: pageId,
        });
        updateFraming(data.framing);
        addMessage('agent', '🔄 已從 Notion 同步！框架已更新。');
    } catch (err) {
        addMessage('agent', `⚠️ 同步失敗：${err.message}`);
    } finally {
        $btnSyncNotion.disabled = false;
    }
}

async function runLogicCheck() {
    if (!state.sessionId) return;
    $btnLogicCheck.disabled = true;
    $btnLogicCheck.querySelector('.btn-icon').textContent = '⏳';

    try {
        const data = await api('/chat/logic-check', {
            session_id: state.sessionId,
        });

        // Display results
        let html = '';

        // Logical gaps
        const gaps = data.logical_gaps || [];
        if (gaps.length > 0) {
            html += '<div class="logic-section"><div class="logic-section-title">⚠️ Logical Gaps</div>';
            gaps.forEach(g => { html += `<div class="logic-item">${g}</div>`; });
            html += '</div>';
        }

        // Scope issues
        const scope = data.scope_issues || [];
        if (scope.length > 0) {
            html += '<div class="logic-section"><div class="logic-section-title">📏 Scope Issues</div>';
            scope.forEach(s => { html += `<div class="logic-item">${s}</div>`; });
            html += '</div>';
        }

        // Assessment
        const assessment = data.alignment_assessment || '';
        if (assessment) {
            html += `<div class="logic-section"><div class="logic-section-title">🎯 Overall Assessment</div>`;
            html += `<div class="logic-assessment">${assessment}</div></div>`;
        }

        if (!html) {
            html = '<div class="logic-item good">✅ 框架結構一致，沒有發現問題！</div>';
        }

        $logicCheckContent.innerHTML = html;
        $logicCheckResults.style.display = 'block';

        addMessage('agent', '🧪 Logic Check 完成！結果顯示在右側面板。');
    } catch (err) {
        addMessage('agent', `⚠️ Logic Check 失敗：${err.message}`);
    } finally {
        $btnLogicCheck.disabled = false;
        $btnLogicCheck.querySelector('.btn-icon').textContent = '🧪';
    }
}

// ---------------------------------------------------------------------------
// Event listeners
// ---------------------------------------------------------------------------

$chatForm.addEventListener('submit', (e) => {
    e.preventDefault();
    sendMessage($chatInput.value);
});

// Auto-resize textarea
$chatInput.addEventListener('input', () => {
    $chatInput.style.height = 'auto';
    $chatInput.style.height = Math.min($chatInput.scrollHeight, 120) + 'px';
});

// Enter = new line (no auto-send), only the send button triggers send

// Notion buttons
$btnSaveNotion.addEventListener('click', saveToNotion);
$btnSyncNotion.addEventListener('click', () => {
    $syncModal.style.display = 'flex';
    $notionPageIdInput.focus();
});
$btnLogicCheck.addEventListener('click', runLogicCheck);

// Modal
$syncCancel.addEventListener('click', () => {
    $syncModal.style.display = 'none';
});
$syncConfirm.addEventListener('click', () => {
    const pageId = $notionPageIdInput.value.trim();
    if (pageId) {
        $syncModal.style.display = 'none';
        syncFromNotion(pageId);
    }
});

// Close modal on overlay click
$syncModal.addEventListener('click', (e) => {
    if (e.target === $syncModal) {
        $syncModal.style.display = 'none';
    }
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

startSession();
