/**
 * OmniDev API & WebSocket Gateway Resolver
 * Enables seamless split-deployment between Vercel (Frontend) and Render (FastAPI Backend)
 */
(() => {
  // Priority order: localStorage > window config > relative (localhost)
  window.getApiBase = function() {
    const custom = localStorage.getItem('omnidev_backend_url');
    if (custom && custom.trim()) {
      return custom.trim().replace(/\/+$/, '');
    }
    if (window.OMNIDEV_BACKEND_URL && window.OMNIDEV_BACKEND_URL.trim()) {
      return window.OMNIDEV_BACKEND_URL.trim().replace(/\/+$/, '');
    }
    // Default to relative if running on localhost / 127.0.0.1
    return '';
  };

  window.setApiBase = function(url) {
    if (!url) {
      localStorage.removeItem('omnidev_backend_url');
    } else {
      localStorage.setItem('omnidev_backend_url', url.trim().replace(/\/+$/, ''));
    }
  };

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

  // Intercept standard fetch to prepend API base if set
  const origFetch = window.fetch;
  window.fetch = function(input, init) {
    if (typeof input === 'string' && input.startsWith('/api/')) {
      const base = window.getApiBase();
      if (base) {
        input = base + input;
      }
    }
    return origFetch(input, init);
  };
})();
