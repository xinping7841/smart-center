(function installSmartCenterLogin(global) {
    'use strict';

async function submitLogin() {
    const username = (document.getElementById('login-username')?.value || '').trim();
    const password = document.getElementById('login-password')?.value || '';
    const remember = !!document.getElementById('remember-me')?.checked;
    const status = document.getElementById('login-status');
    if (!username || !password) {
        status.className = 'status error';
        status.innerText = '请输入用户名和密码';
        return;
    }
    status.className = 'status';
    status.innerText = '正在登录...';
    try {
        const response = await fetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password, remember })
        });
        const data = await response.json();
        if (!data.ok) throw new Error(data.msg || '登录失败');
        if (remember) {
            localStorage.setItem('spm_remember_username', username);
            localStorage.setItem('spm_remember_password', password);
        } else {
            localStorage.removeItem('spm_remember_username');
            localStorage.removeItem('spm_remember_password');
        }
        status.className = 'status success';
        status.innerText = '登录成功，正在进入系统...';
        window.location.href = '/';
    } catch (error) {
        status.className = 'status error';
        status.innerText = error.message || '登录失败';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const usernameInput = document.getElementById('login-username');
    const passwordInput = document.getElementById('login-password');
    const remember = document.getElementById('remember-me');
    const localUsername = localStorage.getItem('spm_remember_username') || '';
    const localPassword = localStorage.getItem('spm_remember_password') || '';
    if (usernameInput && localUsername) usernameInput.value = localUsername;
    if (passwordInput && localPassword) passwordInput.value = localPassword;
    if (remember && (localUsername || localPassword)) remember.checked = true;
    usernameInput?.focus();
    [usernameInput, passwordInput].forEach(el => {
        el?.addEventListener('keydown', event => {
            if (event.key === 'Enter') submitLogin();
        });
    });
});

const api = { submitLogin };
const SmartCenter = global.SmartCenter || (global.SmartCenter = {});
SmartCenter.login = Object.assign({}, SmartCenter.login || {}, api);
if (typeof SmartCenter.registerModule === 'function') {
    SmartCenter.registerModule('login', {
        kind: 'view',
        view: 'login',
        exports: Object.keys(api),
        source: 'static/js/views/login.js',
    });
}
global.submitLogin = submitLogin;
})(window);
