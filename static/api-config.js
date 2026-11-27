/**
 * OmniDev Universal Multi-Tenant Architecture & Session Controller
 * Architecture B: Zero-Leakage Public Multi-User SaaS & Cloud Ingress Resolver
 */
(() => {
  // 1. Backend URL resolution for split deployment (Vercel Frontend + Render Backend)
  const DEFAULT_RENDER_BACKEND = 'https://omnidev-backend-yuf2.onrender.com';

  window.getApiBase = function() {
    const custom = localStorage.getItem('omnidev_backend_url');
    if (custom && custom.trim()) {
      return custom.trim().replace(/\/+$/, '');
    }
    if (window.OMNIDEV_BACKEND_URL && window.OMNIDEV_BACKEND_URL.trim()) {
      return window.OMNIDEV_BACKEND_URL.trim().replace(/\/+$/, '');
    }
    if (location.hostname === 'localhost' || location.hostname === '127.0.0.1') {
      return '';
    }
    return DEFAULT_RENDER_BACKEND;
  };

  window.setApiBase = function(url) {
    if (!url) {
      localStorage.removeItem('omnidev_backend_url');
    } else {
      localStorage.setItem('omnidev_backend_url', url.trim().replace(/\/+$/, ''));
    }
  };

  // 2. Client Session & Repository Targeting (Multi-Tenant Architecture B)
  window.getOmniDevRepo = function() {
    return localStorage.getItem('omnidev_target_repo') || '';
  };

  window.setOmniDevRepo = function(repo) {
    if (!repo || !repo.trim()) {
      localStorage.removeItem('omnidev_target_repo');
    } else {
      let clean = repo.trim()
        .replace(/^https?:\/\/github\.com\//i, '')
        .replace(/\.git$/i, '')
        .replace(/\/+$/, '');
      localStorage.setItem('omnidev_target_repo', clean);
    }
    window.dispatchEvent(new CustomEvent('omnidev:repo-changed', { detail: { repo: window.getOmniDevRepo() } }));
    window.syncOmniDevNav();
  };

  window.getOmniDevToken = function() {
    return localStorage.getItem('omnidev_github_token') || '';
  };

  window.setOmniDevToken = function(token) {
    if (!token || !token.trim()) {
      localStorage.removeItem('omnidev_github_token');
    } else {
      localStorage.setItem('omnidev_github_token', token.trim());
    }
  };

  window.getOmniDevGroqKey = function() {
    return localStorage.getItem('omnidev_groq_key') || '';
  };

  window.setOmniDevGroqKey = function(key) {
    if (!key || !key.trim()) {
      localStorage.removeItem('omnidev_groq_key');
    } else {
      localStorage.setItem('omnidev_groq_key', key.trim());
    }
  };

  window.getOmniDevMaxIterations = function() {
    const raw = parseInt(localStorage.getItem('omnidev_max_iterations') || '15', 10);
    if (isNaN(raw)) return 15;
    return Math.max(1, Math.min(raw, 30));
  };

  window.setOmniDevMaxIterations = function(val) {
    const n = parseInt(val, 10);
    if (isNaN(n)) return;
    localStorage.setItem('omnidev_max_iterations', String(Math.max(1, Math.min(n, 30))));
  };

  window.getOmniDevProfile = function() {
    try {
      const saved = localStorage.getItem('omnidev_user_profile');
      if (saved) return JSON.parse(saved);
    } catch(e) {}
    return {
      name: 'Operator (Guest)',
      email: 'operator@omnidev.internal',
      role: 'Autonomous SRE Operator',
      org: 'OmniDev Cloud',
      avatar: 'OP'
    };
  };

  window.setOmniDevProfile = function(profile) {
    localStorage.setItem('omnidev_user_profile', JSON.stringify(profile));
    window.syncOmniDevNav();
  };

  // 3. WebSocket Resolver
  window.getOmniDevWsUrl = function(path) {
    const base = window.getApiBase();
    if (!base) {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      return proto + '//' + location.host + path;
    }
    try {
      const u = new URL(base);
      const proto = u.protocol === 'https:' ? 'wss:' : 'ws:';
      return proto + '//' + u.host + path;
    } catch(e) {
      const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
      return proto + '//' + location.host + path;
    }
  };

  // 4. Fetch Interceptor: Prepends API base and injects session headers
  const origFetch = window.fetch;
  window.fetch = function(input, init = {}) {
    init = init || {};
    init.headers = init.headers || {};

    let targetRepo = window.getOmniDevRepo();
    let targetToken = window.getOmniDevToken();
    let targetGroqKey = window.getOmniDevGroqKey();

    // Support Headers instance or plain object
    if (init.headers instanceof Headers) {
      if (targetRepo && !init.headers.has('X-Target-Repo')) {
        init.headers.append('X-Target-Repo', targetRepo);
      }
      if (targetToken && !init.headers.has('X-GitHub-Token')) {
        init.headers.append('X-GitHub-Token', targetToken);
      }
      if (targetGroqKey && !init.headers.has('X-Groq-Api-Key')) {
        init.headers.append('X-Groq-Api-Key', targetGroqKey);
      }
    } else if (typeof init.headers === 'object') {
      if (targetRepo && !init.headers['X-Target-Repo']) {
        init.headers['X-Target-Repo'] = targetRepo;
      }
      if (targetToken && !init.headers['X-GitHub-Token']) {
        init.headers['X-GitHub-Token'] = targetToken;
      }
      if (targetGroqKey && !init.headers['X-Groq-Api-Key']) {
        init.headers['X-Groq-Api-Key'] = targetGroqKey;
      }
    }

    if (typeof input === 'string' && input.startsWith('/api/')) {
      const base = window.getApiBase();
      if (base) {
        input = base + input;
      }
    }
    return origFetch(input, init);
  };

  // 5. Universal Navigation & Topbar Synchronizer
  window.syncOmniDevNav = function() {
    const repo = window.getOmniDevRepo();
    const profile = window.getOmniDevProfile();

    // Inject Brand SVG Logo & Favicon
    if (!document.querySelector('link[rel="icon"]')) {
      const fav = document.createElement('link');
      fav.rel = 'icon';
      fav.type = 'image/svg+xml';
      fav.href = '/static/logo.svg';
      document.head.appendChild(fav);
    }
    document.querySelectorAll('.brand-icon').forEach(el => {
      if (!el.dataset.logoApplied) {
        el.innerHTML = '<img src="/static/logo.svg" alt="OmniDev Logo" style="width:100%;height:100%;display:block;border-radius:10px;">';
        el.dataset.logoApplied = 'true';
      }
    });

    // Synchronize Topbar Repo Pills
    const repoPillEls = document.querySelectorAll('#global-repo-pill, #nav-repo-link, #landing-repo-pill, .repo-pill');
    repoPillEls.forEach(el => {
      if (!el) return;
      if (repo) {
        el.href = `https://github.com/${repo}`;
        el.title = `Connected Target: ${repo} (Click to switch)`;
        el.innerHTML = `
          <span class="badge-dot" style="background:var(--success,#10b981);"></span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
          <span style="font-weight:600;">${repo}</span>
        `;
        el.onclick = (e) => {
          if (e.altKey || e.ctrlKey || e.metaKey) return;
          e.preventDefault();
          window.openRepoModal();
        };
      } else {
        el.href = 'javascript:void(0)';
        el.title = 'Click to connect a GitHub repository';
        el.innerHTML = `
          <span class="badge-dot" style="background:var(--warning,#f59e0b);"></span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
          <span style="font-weight:600;">+ Connect Repo</span>
        `;
        el.onclick = (e) => {
          e.preventDefault();
          window.openRepoModal();
        };
      }
    });

    // Synchronize Topbar User Dropdown & Button
    const avatarBtn = document.querySelector('.user-avatar-btn');
    if (avatarBtn) {
      const circle = avatarBtn.querySelector('.user-avatar-circle');
      if (circle) circle.textContent = profile.avatar || 'OP';
      const label = avatarBtn.querySelector('span');
      if (label) label.textContent = (profile.name || 'Operator').split(' ')[0];
    }

    // Point topbar Settings gear to Platform & API Keys tab
    document.querySelectorAll('.topbar-actions a[href="/settings"]').forEach(el => {
      el.href = '/settings#credentials';
      el.title = 'Platform & API Settings';
    });

    const dropdownPanel = document.getElementById('user-dropdown-panel');
    if (dropdownPanel) {
      dropdownPanel.innerHTML = `
        <div style="padding:8px 10px 10px;border-bottom:1px solid var(--border-subtle,#1e293b);margin-bottom:8px;">
          <div style="font-size:13.5px;font-weight:700;color:#fff;">${profile.name || 'Operator (Guest)'}</div>
          <div style="font-size:11.5px;color:var(--text-tertiary,#94a3b8);">${profile.email || 'operator@omnidev.internal'}</div>
          <div style="margin-top:6px;">
            <span class="badge ${repo ? 'badge-success' : 'badge-warning'}" style="font-size:11px;">
              <span class="badge-dot"></span>${repo ? repo : 'No Repo Connected'}
            </span>
          </div>
        </div>
        <a href="/settings#profile" class="dropdown-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
          Account Profile
        </a>
        <a href="/settings#credentials" class="dropdown-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
          Git &amp; API Keys
        </a>
        <a href="javascript:void(0)" onclick="openRepoModal()" class="dropdown-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
          ${repo ? 'Switch Target Repository' : 'Connect Repository'}
        </a>
        <a href="/auth" class="dropdown-item">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg>
          Sign In / Create Account
        </a>
        <div style="border-top:1px solid var(--border-subtle,#1e293b);margin-top:8px;padding-top:8px;">
          <a href="javascript:void(0)" onclick="window.resetOmniDevSession()" class="dropdown-item danger">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/></svg>
            Reset Session
          </a>
        </div>
      `;
    }

    // Ensure Consistent Nav Links
    const navBar = document.querySelector('.topbar-nav');
    if (navBar && !navBar.dataset.navStandardized) {
      const currentPath = window.location.pathname.replace(/\/$/, '') || '/';
      const navItems = [
        { href: '/', label: 'Overview', active: currentPath === '/' || currentPath === '/index' || currentPath === '/static/index.html' },
        { href: '/console', label: 'Nerve Center', active: currentPath === '/console' || currentPath === '/static/console.html' },
        { href: '/workspace', label: 'Codebase', active: currentPath === '/workspace' || currentPath === '/static/workspace.html' },
        { href: '/analytics', label: 'Telemetry', active: currentPath === '/analytics' || currentPath === '/static/analytics.html' },
        { href: '/integrations', label: 'Integrations', active: currentPath === '/integrations' || currentPath === '/static/integrations.html' },
        { href: '/rules', label: 'Playbook', active: currentPath === '/rules' || currentPath === '/static/rules.html' },
        { href: '/docs', label: 'Architecture', active: currentPath === '/docs' || currentPath === '/static/docs.html' }
      ];
      navBar.innerHTML = navItems.map(it => `<a href="${it.href}" class="${it.active ? 'active' : ''}">${it.label}</a>`).join('');
      navBar.dataset.navStandardized = 'true';
    }
  };

  // 6. Universal Repository Switcher Modal
  window.openRepoModal = function() {
    let modal = document.getElementById('omnidev-repo-modal');
    if (!modal) {
      modal = document.createElement('div');
      modal.id = 'omnidev-repo-modal';
      modal.style.cssText = `
        position: fixed; top: 0; left: 0; width: 100vw; height: 100vh;
        background: rgba(0, 0, 0, 0.75); backdrop-filter: blur(10px);
        display: flex; align-items: center; justify-content: center;
        z-index: 10000; animation: fadeIn 0.15s ease;
      `;
      modal.innerHTML = `
        <div style="
          background: #0b0f19; border: 1px solid rgba(255,255,255,0.1);
          box-shadow: 0 25px 60px rgba(0,0,0,0.8), 0 0 30px rgba(99,102,241,0.2);
          border-radius: 14px; width: 92%; max-width: 520px; padding: 26px; color: #fff;
        ">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;">
            <div style="display:flex;align-items:center;gap:10px;">
              <div style="width:36px;height:36px;border-radius:10px;background:rgba(99,102,241,0.15);display:flex;align-items:center;justify-content:center;color:#818cf8;">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/></svg>
              </div>
              <div>
                <h3 style="font-size:17px;font-weight:700;margin:0;">Connect GitHub Repository</h3>
                <div style="font-size:12px;color:#94a3b8;">Multi-tenant session isolation (Architecture B)</div>
              </div>
            </div>
            <button onclick="document.getElementById('omnidev-repo-modal').style.display='none'" style="background:transparent;border:none;color:#94a3b8;cursor:pointer;font-size:20px;line-height:1;">✕</button>
          </div>

          <p style="font-size:13px;color:#cbd5e1;line-height:1.5;margin-bottom:16px;">
            Connect your target GitHub codebase to run automated self-healing, explore repository files, and dispatch AI fix workflows.
          </p>

          <div style="margin-bottom:14px;">
            <label style="display:block;font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:6px;text-transform:uppercase;">Target Repository (owner/repo)</label>
            <input type="text" id="modal-repo-input" placeholder="e.g. facebook/react or your-org/your-app" style="
              width:100%;box-sizing:border-box;background:#131b2e;border:1px solid #1e293b;border-radius:8px;
              color:#fff;padding:10px 14px;font-size:14px;font-family:monospace;outline:none;
            ">
          </div>

          <div style="margin-bottom:14px;">
            <label style="display:block;font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:6px;text-transform:uppercase;">GitHub Personal Access Token (Optional)</label>
            <input type="password" id="modal-token-input" placeholder="ghp_••••••••••••••••••••••••••••••••••••" style="
              width:100%;box-sizing:border-box;background:#131b2e;border:1px solid #1e293b;border-radius:8px;
              color:#fff;padding:10px 14px;font-size:14px;font-family:monospace;outline:none;
            ">
            <div style="font-size:11.5px;color:#64748b;margin-top:4px;">Stored only in your browser. Needed for private repos or automatic PR creation.</div>
          </div>

          <div style="margin-bottom:16px;">
            <label style="display:block;font-size:12px;font-weight:600;color:#94a3b8;margin-bottom:6px;text-transform:uppercase;">Groq API Key (For Live AI Agent)</label>
            <input type="password" id="modal-groq-input" placeholder="gsk_••••••••••••••••••••••••••••••••••••" style="
              width:100%;box-sizing:border-box;background:#131b2e;border:1px solid #1e293b;border-radius:8px;
              color:#fff;padding:10px 14px;font-size:14px;font-family:monospace;outline:none;
            ">
            <div style="font-size:11.5px;color:#64748b;margin-top:4px;">Stored only in your browser (never saved on server DB). Optional if server provides a demo fallback.</div>
          </div>

          <div style="margin-bottom:20px;">
            <div style="font-size:11.5px;font-weight:600;color:#94a3b8;margin-bottom:8px;text-transform:uppercase;">Quick Presets:</div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;">
              <button type="button" class="preset-btn" onclick="document.getElementById('modal-repo-input').value='fastapi/fastapi'" style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:#cbd5e1;padding:5px 10px;border-radius:6px;font-size:12px;font-family:monospace;cursor:pointer;">fastapi/fastapi</button>
              <button type="button" class="preset-btn" onclick="document.getElementById('modal-repo-input').value='pallets/flask'" style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:#cbd5e1;padding:5px 10px;border-radius:6px;font-size:12px;font-family:monospace;cursor:pointer;">pallets/flask</button>
              <button type="button" class="preset-btn" onclick="document.getElementById('modal-repo-input').value='octocat/Hello-World'" style="background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.1);color:#cbd5e1;padding:5px 10px;border-radius:6px;font-size:12px;font-family:monospace;cursor:pointer;">octocat/Hello-World</button>
            </div>
          </div>

          <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid #1e293b;padding-top:16px;">
            <button type="button" onclick="window.clearConnectedRepo()" style="background:transparent;border:1px solid #ef4444;color:#ef4444;border-radius:8px;padding:9px 14px;font-size:13px;font-weight:600;cursor:pointer;">Disconnect</button>
            <div style="display:flex;gap:10px;">
              <button type="button" onclick="document.getElementById('omnidev-repo-modal').style.display='none'" style="background:rgba(255,255,255,0.08);border:none;color:#fff;border-radius:8px;padding:9px 16px;font-size:13px;font-weight:600;cursor:pointer;">Cancel</button>
              <button type="button" onclick="window.saveConnectedRepo()" style="background:#6366f1;border:none;color:#fff;border-radius:8px;padding:9px 20px;font-size:13px;font-weight:600;cursor:pointer;">Save &amp; Connect</button>
            </div>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    document.getElementById('modal-repo-input').value = window.getOmniDevRepo();
    document.getElementById('modal-token-input').value = window.getOmniDevToken();
    const groqInput = document.getElementById('modal-groq-input');
    if (groqInput) groqInput.value = window.getOmniDevGroqKey();
    modal.style.display = 'flex';
  };

  window.saveConnectedRepo = function() {
    const repoInput = document.getElementById('modal-repo-input');
    const tokenInput = document.getElementById('modal-token-input');
    const groqInput = document.getElementById('modal-groq-input');
    const repo = repoInput ? repoInput.value.trim() : '';
    const token = tokenInput ? tokenInput.value.trim() : '';
    const groq = groqInput ? groqInput.value.trim() : '';
    window.setOmniDevRepo(repo);
    window.setOmniDevToken(token);
    if (groqInput) window.setOmniDevGroqKey(groq);
    document.getElementById('omnidev-repo-modal').style.display = 'none';
    if (window.location.pathname.includes('workspace') || window.location.pathname.includes('console')) {
      window.location.reload();
    }
  };

  window.clearConnectedRepo = function() {
    window.setOmniDevRepo('');
    window.setOmniDevToken('');
    document.getElementById('omnidev-repo-modal').style.display = 'none';
    window.location.reload();
  };

  window.resetOmniDevSession = function() {
    if (confirm('Clear all local repository connections, API keys, and reset session?')) {
      localStorage.removeItem('omnidev_target_repo');
      localStorage.removeItem('omnidev_github_token');
      localStorage.removeItem('omnidev_groq_key');
      localStorage.removeItem('omnidev_user_profile');
      window.location.reload();
    }
  };

  window.toggleUserDropdown = function(e) {
    if (e) e.stopPropagation();
    const panel = document.getElementById('user-dropdown-panel');
    if (!panel) return;
    panel.style.display = (panel.style.display === 'none' || !panel.style.display) ? 'block' : 'none';
  };

  // Close dropdown on outside click
  document.addEventListener('click', (e) => {
    const panel = document.getElementById('user-dropdown-panel');
    const btn = document.querySelector('.user-avatar-btn');
    if (panel && panel.style.display === 'block' && btn && !btn.contains(e.target) && !panel.contains(e.target)) {
      panel.style.display = 'none';
    }
  });

  // Run on DOM ready
  const _onReady = () => {
    window.syncOmniDevNav();
    if (new URLSearchParams(window.location.search).get('setup') === '1' && !window.getOmniDevRepo()) {
      window.openRepoModal();
    }
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _onReady);
  } else {
    _onReady();
  }
})();
