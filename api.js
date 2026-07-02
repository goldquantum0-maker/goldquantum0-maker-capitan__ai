const CFG = {
  API: window.location.hostname === 'localhost'
    ? 'http://localhost:8000'
    : 'https://capitan-ai-jxu8.onrender.com',
};

export async function apiCall(endpoint, options = {}) {
  const token = localStorage.getItem('capitan_token');
  const headers = { 'Content-Type': 'application/json', ...options.headers };
  if (token) headers['Authorization'] = 'Bearer ' + token;

  const res = await fetch(CFG.API + endpoint, { ...options, headers });
  if (!res.ok) {
    let err = await res.text();
    try { err = JSON.parse(err).detail || err; } catch {}
    throw new Error(`API error (${res.status}): ${err}`);
  }
  return res.json();
}

export { CFG };