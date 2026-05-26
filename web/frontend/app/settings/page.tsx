'use client';

import { useState, useEffect, useCallback } from 'react';
import { fetcher } from '@/lib/api';

// ─────────────────────────────────────────────────────────────────────────────
// Types
// ─────────────────────────────────────────────────────────────────────────────

interface FieldDef {
  key: string;
  label: string;
  placeholder: string;
  sensitive: boolean;
  hint?: string;
  type?: 'text' | 'select' | 'textarea';
  options?: { value: string; label: string }[];
  envKey: string; // backend status key
}

interface SectionDef {
  id: string;
  title: string;
  icon: string;
  description: string;
  fields: FieldDef[];
}

type ConfigMap = Record<string, string>;
type StatusMap = Record<string, boolean>;

// ─────────────────────────────────────────────────────────────────────────────
// Config schema
// ─────────────────────────────────────────────────────────────────────────────

const SECTIONS: SectionDef[] = [
  {
    id: 'binance',
    title: 'Binance',
    icon: '🏦',
    description: 'API credentials for trading and balance queries',
    fields: [
      {
        key: 'BINANCE_API_KEY',
        envKey: 'BINANCE_API_KEY',
        label: 'API Key',
        placeholder: 'Paste your Binance API key…',
        sensitive: true,
        hint: 'Enable Spot + Futures read & trade permissions. Never enable Withdrawal.',
      },
      {
        key: 'BINANCE_SECRET_KEY',
        envKey: 'BINANCE_SECRET_KEY',
        label: 'Secret Key',
        placeholder: 'Paste your Binance secret key…',
        sensitive: true,
      },
      {
        key: 'BINANCE_TESTNET',
        envKey: 'BINANCE_TESTNET',
        label: 'Use Testnet',
        placeholder: '',
        sensitive: false,
        type: 'select',
        options: [
          { value: 'true', label: '✅ Yes — testnet (safe for testing)' },
          { value: 'false', label: '⚠️  No — real Binance (live money)' },
        ],
        hint: 'Keep true until you have verified signals are working.',
      },
    ],
  },
  {
    id: 'ai',
    title: 'AI APIs',
    icon: '🤖',
    description: 'LLM keys for the dual-advisor and daily reports',
    fields: [
      {
        key: 'CLAUDE_API_KEY',
        envKey: 'CLAUDE_API_KEY',
        label: 'Claude API Key (Anthropic)',
        placeholder: 'sk-ant-…',
        sensitive: true,
        hint: 'Get yours at console.anthropic.com. Uses claude-haiku-4-5.',
      },
      {
        key: 'DEEPSEEK_API_KEY',
        envKey: 'DEEPSEEK_API_KEY',
        label: 'DeepSeek API Key',
        placeholder: 'sk-…',
        sensitive: true,
        hint: 'Get yours at platform.deepseek.com. Uses deepseek-chat (V3).',
      },
    ],
  },
  {
    id: 'telegram',
    title: 'Telegram',
    icon: '📱',
    description: 'Telegram bot for alerts and commands',
    fields: [
      {
        key: 'TELEGRAM_BOT_TOKEN',
        envKey: 'TELEGRAM_BOT_TOKEN',
        label: 'Bot Token',
        placeholder: '123456789:ABCdef…',
        sensitive: true,
        hint: 'Create a bot via @BotFather on Telegram and paste the token here.',
      },
      {
        key: 'TELEGRAM_ALLOWED_USER_IDS',
        envKey: 'TELEGRAM_ALLOWED_USER_IDS',
        label: 'Allowed User IDs',
        placeholder: '123456789,987654321',
        sensitive: false,
        hint: 'Comma-separated Telegram user IDs. Find your ID via @userinfobot.',
      },
    ],
  },
  {
    id: 'web',
    title: 'Web Security',
    icon: '🔐',
    description: 'API key for the dashboard — add to browser env and backend',
    fields: [
      {
        key: 'WEB_API_KEY',
        envKey: 'WEB_API_KEY',
        label: 'Web API Key',
        placeholder: 'my-strong-random-secret',
        sensitive: true,
        hint: 'Set the same value in backend WEB_API_KEY and frontend NEXT_PUBLIC_API_KEY.',
      },
      {
        key: 'NEXT_PUBLIC_API_URL',
        envKey: 'REDIS_URL',       // not directly tracked but we show it
        label: 'Backend URL (for browser)',
        placeholder: 'http://localhost:8000',
        sensitive: false,
        hint: 'URL the browser uses to reach the FastAPI backend. Default: http://localhost:8000.',
      },
    ],
  },
  {
    id: 'advanced',
    title: 'Advanced',
    icon: '⚙️',
    description: 'Engine tuning — safe to leave at defaults',
    fields: [
      {
        key: 'SCAN_INTERVAL_SECONDS',
        envKey: 'SCAN_INTERVAL_SECONDS',
        label: 'Scan Interval (seconds)',
        placeholder: '300',
        sensitive: false,
        hint: 'How often the engine checks each pair for signals. Default: 300 (5 min).',
      },
      {
        key: 'REPORT_TIMES',
        envKey: 'REPORT_TIMES',
        label: 'Daily Report Times (UTC)',
        placeholder: '07:00,12:00,17:00,22:00',
        sensitive: false,
        hint: 'Comma-separated HH:MM UTC times for the 4 daily Telegram reports.',
      },
      {
        key: 'REDIS_URL',
        envKey: 'REDIS_URL',
        label: 'Redis URL',
        placeholder: 'redis://redis:6379',
        sensitive: false,
        hint: 'Only change if Redis runs on a custom host/port.',
      },
    ],
  },
];

const STORAGE_KEY = 'bot_config_v1';

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────

function loadFromStorage(): ConfigMap {
  if (typeof window === 'undefined') return {};
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}');
  } catch {
    return {};
  }
}

function saveToStorage(cfg: ConfigMap) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cfg));
}

function generateEnvContent(cfg: ConfigMap): string {
  const lines: string[] = [
    '# ═══════════════════════════════════════════════════════',
    '#  Crypto Trading Bot — .env (generated by Settings UI)',
    '# ═══════════════════════════════════════════════════════',
    '',
    '# Binance',
    `BINANCE_API_KEY=${cfg.BINANCE_API_KEY ?? ''}`,
    `BINANCE_SECRET_KEY=${cfg.BINANCE_SECRET_KEY ?? ''}`,
    `BINANCE_TESTNET=${cfg.BINANCE_TESTNET ?? 'true'}`,
    '',
    '# AI APIs',
    `CLAUDE_API_KEY=${cfg.CLAUDE_API_KEY ?? ''}`,
    `DEEPSEEK_API_KEY=${cfg.DEEPSEEK_API_KEY ?? ''}`,
    '',
    '# Telegram',
    `TELEGRAM_BOT_TOKEN=${cfg.TELEGRAM_BOT_TOKEN ?? ''}`,
    `TELEGRAM_ALLOWED_USER_IDS=${cfg.TELEGRAM_ALLOWED_USER_IDS ?? ''}`,
    '',
    '# Web Dashboard',
    `WEB_API_KEY=${cfg.WEB_API_KEY ?? 'change-me-secret'}`,
    `NEXT_PUBLIC_API_URL=${cfg.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}`,
    `NEXT_PUBLIC_API_KEY=${cfg.WEB_API_KEY ?? 'change-me-secret'}`,
    '',
    '# Advanced',
    `REDIS_URL=${cfg.REDIS_URL ?? 'redis://redis:6379'}`,
    `SCAN_INTERVAL_SECONDS=${cfg.SCAN_INTERVAL_SECONDS ?? '300'}`,
    `REPORT_TIMES=${cfg.REPORT_TIMES ?? '07:00,12:00,17:00,22:00'}`,
  ];
  return lines.join('\n');
}

// ─────────────────────────────────────────────────────────────────────────────
// Sub-components
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ configured }: { configured: boolean | undefined }) {
  if (configured === undefined) {
    return <span className="text-xs text-gray-500 font-mono">···</span>;
  }
  return configured ? (
    <span className="inline-flex items-center gap-1 text-xs text-green-400 font-medium">
      <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
      active
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 text-xs text-gray-500 font-medium">
      <span className="h-1.5 w-1.5 rounded-full bg-gray-600" />
      not set
    </span>
  );
}

function CopyButton({ text, label = 'Copy' }: { text: string; label?: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <button
      onClick={handleCopy}
      className="px-3 py-1.5 rounded text-xs font-medium bg-gray-700 hover:bg-gray-600
                 text-gray-200 transition-colors flex items-center gap-1.5"
    >
      {copied ? '✓ Copied!' : `📋 ${label}`}
    </button>
  );
}

interface FieldInputProps {
  field: FieldDef;
  value: string;
  status: boolean | undefined;
  onChange: (key: string, val: string) => void;
}

function FieldInput({ field, value, status, onChange }: FieldInputProps) {
  const [show, setShow] = useState(false);

  if (field.type === 'select' && field.options) {
    return (
      <div className="space-y-1.5">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-gray-200">{field.label}</label>
          <StatusBadge configured={status} />
        </div>
        <select
          value={value || field.options[0].value}
          onChange={e => onChange(field.key, e.target.value)}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-sm
                     text-white focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
        >
          {field.options.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {field.hint && <p className="text-xs text-gray-500">{field.hint}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <label className="text-sm font-medium text-gray-200">{field.label}</label>
        <StatusBadge configured={status} />
      </div>
      <div className="relative">
        <input
          type={field.sensitive && !show ? 'password' : 'text'}
          value={value}
          onChange={e => onChange(field.key, e.target.value)}
          placeholder={field.placeholder}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 pr-20 text-sm
                     text-white placeholder-gray-600 focus:outline-none focus:border-blue-500
                     focus:ring-1 focus:ring-blue-500 font-mono"
        />
        <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
          {value && <CopyButton text={value} />}
          {field.sensitive && (
            <button
              onClick={() => setShow(s => !s)}
              className="p-1 text-gray-400 hover:text-gray-200 transition-colors"
              title={show ? 'Hide' : 'Show'}
            >
              {show ? '🙈' : '👁'}
            </button>
          )}
        </div>
      </div>
      {field.hint && <p className="text-xs text-gray-500">{field.hint}</p>}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function SettingsPage() {
  const [config, setConfig] = useState<ConfigMap>({});
  const [status, setStatus] = useState<StatusMap | null>(null);
  const [activeSection, setActiveSection] = useState('binance');
  const [saved, setSaved] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    setConfig(loadFromStorage());
  }, []);

  // Fetch backend status (which keys are active in the running container)
  useEffect(() => {
    fetcher('/api/config/status')
      .then((data: StatusMap) => setStatus(data))
      .catch(() => setStatus(null));
  }, []);

  const handleChange = useCallback((key: string, val: string) => {
    setConfig(prev => {
      const next = { ...prev, [key]: val };
      saveToStorage(next);
      return next;
    });
  }, []);

  const handleSaveAll = () => {
    saveToStorage(config);
    setSaved(true);
    setTimeout(() => setSaved(false), 2500);
  };

  const envContent = generateEnvContent(config);

  const currentSection = SECTIONS.find(s => s.id === activeSection) ?? SECTIONS[0];

  // Count configured fields per section
  const sectionProgress = (section: SectionDef): { done: number; total: number } => {
    const total = section.fields.filter(f => f.sensitive || f.type === 'select').length;
    const done = section.fields.filter(f => {
      const val = config[f.key] ?? '';
      return val.length > 0;
    }).length;
    return { done, total };
  };

  return (
    <div className="space-y-6 pb-16">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold">Settings</h1>
          <p className="text-sm text-gray-400 mt-1">
            Fill in your API keys, then click{' '}
            <span className="text-blue-400 font-medium">Generate .env</span> to get the file
            ready for Docker Compose.
          </p>
        </div>
        <button
          onClick={handleSaveAll}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
            saved
              ? 'bg-green-600 text-white'
              : 'bg-blue-600 hover:bg-blue-700 text-white'
          }`}
        >
          {saved ? '✓ Saved to browser' : 'Save to browser'}
        </button>
      </div>

      {/* Status banner */}
      {status === null && (
        <div className="rounded-lg border border-yellow-800 bg-yellow-900/20 px-4 py-3 text-sm text-yellow-300">
          ⚠️ Cannot reach the backend — showing form only.
          Status indicators will appear once the bot is running.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Sidebar */}
        <nav className="lg:col-span-1 space-y-1">
          {SECTIONS.map(section => {
            const { done, total } = sectionProgress(section);
            const isActive = section.id === activeSection;
            return (
              <button
                key={section.id}
                onClick={() => setActiveSection(section.id)}
                className={`w-full text-left px-4 py-3 rounded-xl flex items-center gap-3 transition-all ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'hover:bg-gray-800 text-gray-300'
                }`}
              >
                <span className="text-lg">{section.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">{section.title}</div>
                  {total > 0 && (
                    <div className={`text-xs ${isActive ? 'text-blue-200' : 'text-gray-500'}`}>
                      {done}/{total} filled
                    </div>
                  )}
                </div>
                {done === total && total > 0 && (
                  <span className="text-green-400 text-xs">✓</span>
                )}
              </button>
            );
          })}

          {/* Backend status summary */}
          {status && (
            <div className="mt-4 rounded-xl border border-gray-800 bg-gray-900 p-3 space-y-1.5">
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wide mb-2">
                Active in container
              </p>
              {Object.entries(status).map(([k, v]) => (
                <div key={k} className="flex items-center justify-between text-xs">
                  <span className="text-gray-500 font-mono truncate pr-2">{k}</span>
                  <span className={v ? 'text-green-400' : 'text-gray-600'}>
                    {v ? '✓' : '—'}
                  </span>
                </div>
              ))}
            </div>
          )}
        </nav>

        {/* Form panel */}
        <div className="lg:col-span-3 space-y-6">
          <div className="card space-y-6">
            <div className="border-b border-gray-800 pb-4">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <span>{currentSection.icon}</span>
                {currentSection.title}
              </h2>
              <p className="text-sm text-gray-400 mt-0.5">{currentSection.description}</p>
            </div>

            {currentSection.fields.map(field => (
              <FieldInput
                key={field.key}
                field={field}
                value={config[field.key] ?? ''}
                status={status ? status[field.envKey] : undefined}
                onChange={handleChange}
              />
            ))}
          </div>

          {/* Section navigation */}
          <div className="flex justify-between">
            <button
              onClick={() => {
                const idx = SECTIONS.findIndex(s => s.id === activeSection);
                if (idx > 0) setActiveSection(SECTIONS[idx - 1].id);
              }}
              disabled={activeSection === SECTIONS[0].id}
              className="px-4 py-2 rounded-lg text-sm bg-gray-800 hover:bg-gray-700
                         text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              ← Previous
            </button>
            <button
              onClick={() => {
                const idx = SECTIONS.findIndex(s => s.id === activeSection);
                if (idx < SECTIONS.length - 1) setActiveSection(SECTIONS[idx + 1].id);
              }}
              disabled={activeSection === SECTIONS[SECTIONS.length - 1].id}
              className="px-4 py-2 rounded-lg text-sm bg-gray-800 hover:bg-gray-700
                         text-gray-300 disabled:opacity-30 disabled:cursor-not-allowed transition"
            >
              Next →
            </button>
          </div>
        </div>
      </div>

      {/* .env Generator */}
      <div className="card space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold">📄 Generate .env File</h2>
            <p className="text-sm text-gray-400 mt-0.5">
              Copy this content into{' '}
              <code className="text-blue-400 bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">
                .env
              </code>{' '}
              at the project root, then run{' '}
              <code className="text-blue-400 bg-gray-800 px-1.5 py-0.5 rounded text-xs font-mono">
                docker compose up -d
              </code>
            </p>
          </div>
          <CopyButton text={envContent} label="Copy .env" />
        </div>

        <pre className="bg-gray-950 border border-gray-800 rounded-xl p-4 text-xs
                        font-mono text-gray-300 overflow-x-auto whitespace-pre-wrap
                        leading-relaxed max-h-80 overflow-y-auto">
          {envContent}
        </pre>

        {/* Quick-start steps */}
        <div className="rounded-xl bg-gray-800/50 border border-gray-700 p-4 space-y-2">
          <p className="text-sm font-medium text-gray-200">🚀 Quick-start checklist</p>
          <ol className="text-sm text-gray-400 space-y-1.5 list-none">
            {[
              'Copy the .env content above into the project root .env file',
              'Set BINANCE_TESTNET=false only when you\'re ready for real trading',
              'Run: docker compose up -d',
              'Open the Dashboard at http://localhost:3000',
              'Open Telegram, send /start to your bot to verify it responds',
            ].map((step, i) => (
              <li key={i} className="flex gap-2">
                <span className="text-blue-500 font-mono flex-shrink-0">
                  {String(i + 1).padStart(2, '0')}.
                </span>
                {step}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
