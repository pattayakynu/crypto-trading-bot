/**
 * Settings page — render and interaction tests.
 */
import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';

// Mock fetch for config/status calls
global.fetch = jest.fn();

const FULL_STATUS = {
  BINANCE_API_KEY: false,
  BINANCE_SECRET_KEY: false,
  BINANCE_TESTNET: false,
  CLAUDE_API_KEY: false,
  DEEPSEEK_API_KEY: false,
  TELEGRAM_BOT_TOKEN: false,
  TELEGRAM_ALLOWED_USER_IDS: false,
  WEB_API_KEY: false,
  REDIS_URL: false,
  SCAN_INTERVAL_SECONDS: false,
  REPORT_TIMES: false,
};

function mockFetch(body: unknown, ok = true) {
  (global.fetch as jest.Mock).mockResolvedValueOnce({
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
  });
}

// Mock localStorage
const localStorageMock = (() => {
  let store: Record<string, string> = {};
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; },
    clear: () => { store = {}; },
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

// Mock clipboard
Object.assign(navigator, {
  clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
});

import SettingsPage from '../app/settings/page';

beforeEach(() => {
  (global.fetch as jest.Mock).mockClear();
  localStorageMock.clear();
});

describe('SettingsPage', () => {
  it('renders all section tabs in sidebar', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    // Use getAllByText since section name also appears in the form heading
    expect(screen.getAllByText('Binance').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('AI APIs')).toBeInTheDocument();
    expect(screen.getByText('Telegram')).toBeInTheDocument();
    expect(screen.getByText('Web Security')).toBeInTheDocument();
    expect(screen.getByText('Advanced')).toBeInTheDocument();
  });

  it('shows Binance section fields by default', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    expect(screen.getByText('API Key')).toBeInTheDocument();
    expect(screen.getByText('Secret Key')).toBeInTheDocument();
    expect(screen.getByText('Use Testnet')).toBeInTheDocument();
  });

  it('switches to AI APIs section on click', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    // Click the sidebar button (first occurrence of "AI APIs" is in nav)
    fireEvent.click(screen.getByText('AI APIs'));
    expect(screen.getByText('Claude API Key (Anthropic)')).toBeInTheDocument();
    expect(screen.getByText('DeepSeek API Key')).toBeInTheDocument();
  });

  it('switches to Telegram section on click', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    fireEvent.click(screen.getByText('Telegram'));
    expect(screen.getByText('Bot Token')).toBeInTheDocument();
    expect(screen.getByText('Allowed User IDs')).toBeInTheDocument();
  });

  it('saves values to localStorage on input', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    // Select all inputs (password inputs are present; query by placeholder)
    const apiKeyInput = screen.getByPlaceholderText('Paste your Binance API key…');
    fireEvent.change(apiKeyInput, { target: { value: 'my-api-key-test' } });
    const stored = JSON.parse(localStorageMock.getItem('bot_config_v1') ?? '{}');
    expect(stored.BINANCE_API_KEY).toBe('my-api-key-test');
  });

  it('shows .env generator section with copy button', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    expect(screen.getByText('📄 Generate .env File')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy \.env/i })).toBeInTheDocument();
  });

  it('renders .env content with all keys', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    const pre = document.querySelector('pre');
    expect(pre?.textContent).toContain('BINANCE_API_KEY=');
    expect(pre?.textContent).toContain('CLAUDE_API_KEY=');
    expect(pre?.textContent).toContain('TELEGRAM_BOT_TOKEN=');
    expect(pre?.textContent).toContain('WEB_API_KEY=');
  });

  it('fills .env content with typed values', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    const apiKeyInput = screen.getByPlaceholderText('Paste your Binance API key…');
    fireEvent.change(apiKeyInput, { target: { value: 'abc-binance-key' } });
    const pre = document.querySelector('pre');
    expect(pre?.textContent).toContain('BINANCE_API_KEY=abc-binance-key');
  });

  it('shows warning banner when backend is unreachable', async () => {
    (global.fetch as jest.Mock).mockRejectedValueOnce(new Error('Network error'));
    await act(async () => render(<SettingsPage />));
    expect(screen.getByText(/cannot reach the backend/i)).toBeInTheDocument();
  });

  it('shows status indicators when backend responds with configured keys', async () => {
    mockFetch({ ...FULL_STATUS, BINANCE_API_KEY: true, BINANCE_SECRET_KEY: true });
    await act(async () => render(<SettingsPage />));
    // Should show "active" badge for configured keys
    const activeBadges = screen.getAllByText('active');
    expect(activeBadges.length).toBeGreaterThanOrEqual(1);
  });

  it('shows quickstart checklist', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    expect(screen.getByText(/quick-start checklist/i)).toBeInTheDocument();
    expect(screen.getAllByText(/docker compose up/i).length).toBeGreaterThanOrEqual(1);
  });

  it('Next button advances to AI APIs section', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    const nextBtn = screen.getByRole('button', { name: /next →/i });
    fireEvent.click(nextBtn);
    expect(screen.getByText('Claude API Key (Anthropic)')).toBeInTheDocument();
  });

  it('Previous button is disabled on first section', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    const prevBtn = screen.getByRole('button', { name: /← previous/i });
    expect(prevBtn).toBeDisabled();
  });

  it('Save to browser button shows confirmation feedback', async () => {
    mockFetch(FULL_STATUS);
    await act(async () => render(<SettingsPage />));
    const saveBtn = screen.getByRole('button', { name: /save to browser/i });
    fireEvent.click(saveBtn);
    expect(screen.getByRole('button', { name: /✓ saved to browser/i })).toBeInTheDocument();
  });
});
