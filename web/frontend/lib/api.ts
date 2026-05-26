// Read env vars at call time so tests can override them via process.env
function getApiUrl(): string {
  return process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
}

function getApiKey(): string {
  return process.env.NEXT_PUBLIC_API_KEY || '';
}

export function apiHeaders(): HeadersInit {
  return { 'X-API-Key': getApiKey() };
}

export async function fetcher(path: string) {
  const res = await fetch(`${getApiUrl()}${path}`, {
    headers: apiHeaders(),
    cache: 'no-store',
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function postCommand(path: string) {
  const res = await fetch(`${getApiUrl()}${path}`, {
    method: 'POST',
    headers: apiHeaders(),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export function wsUrl(): string {
  const base = getApiUrl().replace(/^http/, 'ws');
  return `${base}/api/ws/events`;
}
