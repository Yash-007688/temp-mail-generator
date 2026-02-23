async function api(path, options) {
    const res = await fetch(path, Object.assign({
        headers: {
            'Content-Type': 'application/json'
        },
        credentials: 'same-origin'
    }, options));
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
        throw new Error(data.error || `Request failed with status ${res.status}`);
    }
    return data;
}

function setCurrentEmail(email) {
    const input = document.getElementById('email-display');
    if (input) input.value = email || '';
}

function showStatus(msg, isError = false) {
    const statusDiv = document.getElementById('status-msg') || console.log(msg);
    if (!statusDiv) return;
    statusDiv.textContent = msg;
    statusDiv.style.color = isError ? 'var(--danger)' : 'var(--success)';
    statusDiv.classList.remove('hidden');
    setTimeout(() => statusDiv.classList.add('hidden'), 5000);
}

async function refreshInbox() {
    try {
        const btn = document.getElementById('btn-refresh-inbox') || document.getElementById('btn-refresh');
        if (btn) btn.classList.add('loading');

        const data = await api('/inbox');
        setCurrentEmail(data.email);
        const list = document.getElementById('inbox-list');
        list.innerHTML = '';
        (data.messages || []).forEach(msg => {
            const li = document.createElement('li');
            li.innerHTML = `
                <div style="font-weight: 600;">${msg.from}</div>
                <div style="font-size: 0.9rem; color: var(--text-muted);">${msg.subject || '(no subject)'}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted); text-align: right;">${msg.date || ''}</div>
            `;
            li.onclick = () => readEmail(msg.id);
            list.appendChild(li);
        });
    } catch (e) {
        console.error(e);
        showStatus('Failed to refresh inbox: ' + e.message, true);
    } finally {
        const btn = document.getElementById('btn-refresh-inbox') || document.getElementById('btn-refresh');
        if (btn) btn.classList.remove('loading');
    }
}

async function readEmail(id) {
    try {
        const data = await api(`/read/${id}`);
        const pre = document.getElementById('email-view');
        if (!pre) return;

        const body = data.textBody || data.body || '';
        pre.textContent = `From: ${data.from}\nSubject: ${data.subject}\nDate: ${data.date}\n\n${body}`;
        pre.classList.remove('hidden');
    } catch (e) {
        console.error(e);
        showStatus('Failed to read email: ' + e.message, true);
    }
}

async function generateRandom() {
    const btn = document.getElementById('btn-gen-random');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Generating...';
    }
    try {
        const inputLen = document.getElementById('random-length');
        const len = parseInt((inputLen && inputLen.value) || '10', 10);
        const data = await api('/generate/random', {
            method: 'POST',
            body: JSON.stringify({
                length: len
            })
        });
        setCurrentEmail(data.email);
        showStatus('New email generated!');
        await refreshInbox();
    } catch (e) {
        console.error(e);
        showStatus('Generation failed: ' + e.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Generate Random';
        }
    }
}

async function generateCustom(customUsername, customDomain) {
    const btn = document.getElementById('btn-gen-custom');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Creating...';
    }
    try {
        const username = customUsername || document.getElementById('custom-username').value.trim();
        const domain = customDomain || document.getElementById('custom-domain').value.trim() || undefined;
        if (!username) {
            showStatus('Username required', true);
            return;
        }
        const data = await api('/generate/custom', {
            method: 'POST',
            body: JSON.stringify({
                username,
                domain
            })
        });
        setCurrentEmail(data.email);
        showStatus('Custom email created!');
        await refreshInbox();
    } catch (e) {
        console.error(e);
        showStatus(e.message, true);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Create Custom Email';
        }
    }
}

async function exportInbox() {
    try {
        const data = await api('/export', {
            method: 'POST',
            body: JSON.stringify({})
        });
        showStatus(`Saved ${data.saved} email(s)`);
    } catch (e) {
        console.error(e);
        showStatus('Export failed: ' + e.message, true);
    }
}

function bindIfPresent(id, handler) {
    const el = document.getElementById(id);
    if (el) el.onclick = handler;
}

const btnCopy = document.getElementById('btn-copy');
if (btnCopy) btnCopy.onclick = async () => {
    const v = (document.getElementById('email-display').value || '').trim();
    if (!v) return;
    try {
        await navigator.clipboard.writeText(v);
        showStatus('Address copied!');
    } catch {
        showStatus('Failed to copy', true);
    }
};

const btnRefreshInbox = document.getElementById('btn-refresh-inbox');
if (btnRefreshInbox) btnRefreshInbox.onclick = refreshInbox;

const btnChange = document.getElementById('btn-change');
if (btnChange) btnChange.onclick = () => {
    const u = prompt('Enter new username');
    if (!u) return;
    const d = prompt('Enter domain (optional)') || undefined;
    api('/generate/custom', {
        method: 'POST',
        body: JSON.stringify({
            username: u,
            domain: d
        })
    })
        .then(data => {
            setCurrentEmail(data.email);
            refreshInbox();
            showStatus('Email changed!');
        })
        .catch(err => {
            showStatus(err.message, true);
        });
};

const btnDelete = document.getElementById('btn-delete');
if (btnDelete) btnDelete.onclick = () => {
    setCurrentEmail('');
    document.getElementById('inbox-list').innerHTML = '';
    const pre = document.getElementById('email-view');
    if (pre) {
        pre.textContent = '';
        pre.classList.add('hidden');
    }
    showStatus('Session cleared');
};

window.refreshInbox = refreshInbox;

// Settings modal
const settingsModal = document.getElementById('settings-modal');
const btnSettings = document.getElementById('btn-settings');
const settingsClose = document.getElementById('settings-close');
const settingsCancel = document.getElementById('settings-cancel');
const settingsSave = document.getElementById('settings-save');
const settingsUsername = document.getElementById('settings-username');
const settingsDomain = document.getElementById('settings-domain');

let currentUser = null;

function closeSettings() {
    if (!settingsModal) return;
    settingsModal.classList.add('hidden');
}

if (settingsClose) settingsClose.onclick = closeSettings;
if (settingsCancel) settingsCancel.onclick = closeSettings;
if (btnSettings) btnSettings.onclick = openSettings;

async function saveSettings() {
    if (!currentUser || currentUser.plan === 'free') {
        showStatus('₹99 Starter plan or higher required to save settings', true);
        return;
    }

    const username = (settingsUsername && settingsUsername.value.trim()) || '';
    const domain = (settingsDomain && settingsDomain.value.trim()) || '';

    if (!username) {
        showStatus('Username is required', true);
        return;
    }

    try {
        const data = await api('/settings', {
            method: 'POST',
            body: JSON.stringify({
                username,
                domain
            })
        });
        showStatus(data.message);
        await refreshAuth(); // Update local state
        closeSettings();
    } catch (e) {
        showStatus(e.message, true);
    }
}

if (settingsSave) settingsSave.onclick = saveSettings;

function openSettings() {
    if (!settingsModal) return;
    if (currentUser && currentUser.plan === 'free') {
        showStatus('Settings are locked for Free users. Upgrade to Start!', true);
    }

    // Fill from preferences if available
    if (currentUser && currentUser.preferences) {
        try {
            const prefs = JSON.parse(currentUser.preferences);
            if (settingsUsername) settingsUsername.value = prefs.username || '';
            if (settingsDomain) settingsDomain.value = prefs.domain || '';
        } catch (e) { }
    }

    settingsModal.classList.remove('hidden');
}

// Auth state
async function refreshAuth() {
    try {
        const me = await api('/me');
        currentUser = me.user;
        const user = me.user;
        const loginLink = document.getElementById('btn-login');
        const logoutBtn = document.getElementById('btn-logout');
        const settingsBtn = document.getElementById('btn-settings');
        const upgradeBtn = document.getElementById('btn-upgrade');

        if (user) {
            if (loginLink) loginLink.classList.add('hidden');
            if (logoutBtn) logoutBtn.classList.remove('hidden');

            // Plan-based UI visibility
            if (user.plan === 'free') {
                if (settingsBtn) settingsBtn.classList.add('hidden');
                if (upgradeBtn) upgradeBtn.classList.remove('hidden');
            } else {
                if (settingsBtn) settingsBtn.classList.remove('hidden');
                if (upgradeBtn) upgradeBtn.classList.add('hidden');
            }

            // If user has saved preferences and no email is set yet, auto-gen or set it
            if (user.preferences) {
                try {
                    const prefs = JSON.parse(user.preferences);
                    if (prefs.username && !document.getElementById('email-display').value) {
                        generateCustom(prefs.username, prefs.domain);
                    }
                } catch (e) { }
            }
        } else {
            if (loginLink) loginLink.classList.remove('hidden');
            if (logoutBtn) logoutBtn.classList.add('hidden');
            if (settingsBtn) settingsBtn.classList.add('hidden');
            if (upgradeBtn) upgradeBtn.classList.add('hidden');
        }
    } catch (e) {
        console.error(e);
    }
}

const logoutBtn = document.getElementById('btn-logout');
if (logoutBtn) logoutBtn.onclick = async () => {
    try {
        await api('/logout', {
            method: 'POST'
        });
        location.href = '/';
    } catch { }
};

function initUI() {
    bindIfPresent('btn-gen-random', generateRandom);
    bindIfPresent('btn-gen-custom', generateCustom);
    bindIfPresent('btn-refresh', refreshInbox);
    bindIfPresent('btn-export', exportInbox);

    // Copy button re-bind
    const btnCopy2 = document.getElementById('btn-copy');
    if (btnCopy2) btnCopy2.onclick = btnCopy ? btnCopy.onclick : async () => { };

    // Refresh pill re-bind
    const btnRefreshInbox2 = document.getElementById('btn-refresh-inbox');
    if (btnRefreshInbox2) btnRefreshInbox2.onclick = refreshInbox;
}

document.addEventListener('DOMContentLoaded', () => {
    try {
        initUI();
    } catch (e) {
        console.error(e);
    }
    refreshAuth();
});
