import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  Download,
  FileText,
  FlaskConical,
  LayoutDashboard,
  LoaderCircle,
  LockKeyhole,
  LogOut,
  Menu,
  MessageSquare,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Upload,
  UserCheck,
  X,
} from 'lucide-react';
import type { DemoPersona, Detail, ReportSummary, Result, Session, Status } from './types';
import './styles.css';

const STATUSES: Status[] = ['Normal', 'Low', 'High', 'Urgent', 'Cannot Be Classified'];

const STATUS_BADGE_CLASS: Record<Status, string> = {
  Normal: 'bg-emerald-50 text-emerald-800 border-emerald-200',
  Low: 'bg-amber-50 text-amber-800 border-amber-200',
  High: 'bg-amber-50 text-amber-800 border-amber-200',
  Urgent: 'bg-red-50 text-red-800 border-red-200 font-semibold',
  'Cannot Be Classified': 'bg-slate-100 text-slate-700 border-slate-300',
};

const STATUS_DOT_CLASS: Record<Status, string> = {
  Normal: 'bg-emerald-600',
  Low: 'bg-amber-600',
  High: 'bg-amber-600',
  Urgent: 'bg-red-600',
  'Cannot Be Classified': 'bg-slate-500',
};

const NAVIGATION = [
  { name: 'Dashboard', icon: LayoutDashboard },
  { name: 'Patient Reports', icon: ClipboardList },
  { name: 'Report Analysis', icon: Activity },
  { name: 'AI Assistant', icon: MessageSquare },
  { name: 'Report Downloads', icon: Download },
] as const;

type PageName = (typeof NAVIGATION)[number]['name'];

function displayStatus(s: Status): string {
  return s === 'Cannot Be Classified' ? 'Unclassified' : s;
}

function formatDate(s: string | null): string {
  if (!s) return 'Not provided';
  const parsed = new Date(s);
  if (Number.isNaN(parsed.getTime())) return s;
  return new Intl.DateTimeFormat('en', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(parsed);
}

function Brand() {
  return (
    <div className="flex items-center gap-3">
      <span className="grid h-10 w-10 place-items-center rounded-lg border border-teal-200 bg-teal-50 text-teal-700">
        <FlaskConical size={20} strokeWidth={1.8} />
      </span>
      <div className="leading-tight">
        <div className="text-lg font-bold tracking-tight text-slate-900">CityLab</div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Diagnostics</div>
      </div>
    </div>
  );
}

function EvidenceDrawer({ result }: { result: Result }) {
  return (
    <div className="border-b border-slate-200 bg-slate-50 px-6 py-5 text-slate-700">
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="space-y-4">
          <div>
            <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              Plain-Language Explanation
            </div>
            <p className="mt-1.5 text-sm leading-relaxed text-slate-800">{result.explanation || result.reason}</p>
          </div>

          {result.warnings.length > 0 && (
            <div className="space-y-1.5 rounded-md border border-red-200 bg-red-50 p-3 text-xs text-red-900">
              {result.warnings.map((w) => (
                <div key={w} className="flex items-start gap-2 font-medium">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0 text-red-700" />
                  <span>{w}</span>
                </div>
              ))}
            </div>
          )}

          {result.audit.length > 0 && (
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                Deterministic Rule &amp; Calculation Trail
              </div>
              <ul className="mt-2 space-y-1.5 text-xs text-slate-700">
                {result.audit.map((step, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-700" />
                    <span className="font-mono text-[11px] leading-relaxed">{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            Source Evidence Citations ({result.evidence.length})
          </div>
          <div className="mt-2 space-y-2.5">
            {result.evidence.map((ev, i) => (
              <div key={i} className="rounded-md border border-slate-200 bg-white p-3">
                <div className="text-[11px] font-semibold text-teal-800">
                  {ev.file} · {ev.location}
                </div>
                <pre className="mt-1.5 whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-slate-600">
                  {ev.excerpt}
                </pre>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function App() {
  const [accessKey, setAccessKey] = useState('');
  const [draftKey, setDraftKey] = useState('');
  const [personas, setPersonas] = useState<DemoPersona[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selectedReportId, setSelectedReportId] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);

  const [page, setPage] = useState<PageName>('Dashboard');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const [statusFilter, setStatusFilter] = useState<string>('All results');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedRowId, setExpandedRowId] = useState<string | null>(null);

  const [question, setQuestion] = useState('');
  const [chatHistory, setChatHistory] = useState<
    { role: 'user' | 'assistant'; text: string; mode?: string; evidence_ids?: string[] }[]
  >([]);
  const [chatBusy, setChatBusy] = useState(false);

  const [draftAge, setDraftAge] = useState('');
  const [draftSex, setDraftSex] = useState<'female' | 'male' | 'unknown'>('unknown');

  const uploadInputRef = useRef<HTMLInputElement>(null);
  const requestVersionRef = useRef(0);
  const chatEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch('/api/demo/sessions')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.enabled && Array.isArray(data.personas)) {
          setPersonas(data.personas);
        }
      })
      .catch(() => {
        // Ignore if backend is still starting up
      });
  }, []);

  async function apiFetch(path: string, init: RequestInit = {}, tokenOverride = accessKey) {
    const response = await fetch(`/api${path}`, {
      ...init,
      headers: {
        Authorization: `Bearer ${tokenOverride}`,
        ...init.headers,
      },
    });
    if (!response.ok) {
      let message = 'The request could not be completed.';
      try {
        const body = await response.json();
        message = body.detail || message;
      } catch {
        // Non-JSON proxy error
      }
      throw new Error(message);
    }
    return response;
  }

  async function authenticateWithToken(tokenToUse: string) {
    setError('');
    setNotice('');
    setBusy(true);
    try {
      const currentSession: Session = await (await apiFetch('/session', {}, tokenToUse)).json();
      const reportList = await (await apiFetch('/reports', {}, tokenToUse)).json();
      setAccessKey(tokenToUse);
      setDraftKey('');
      setSession(currentSession);
      setReports(reportList.reports || []);
      setSelectedReportId(reportList.reports?.[0]?.id || '');
      setPage('Dashboard');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function handleLoginSubmit(e: React.FormEvent) {
    e.preventDefault();
    authenticateWithToken(draftKey.trim());
  }

  function logout() {
    requestVersionRef.current++;
    setAccessKey('');
    setSession(null);
    setDetail(null);
    setReports([]);
    setSelectedReportId('');
    setChatHistory([]);
    setError('');
    setNotice('');
    setPage('Dashboard');
    setBusy(false);
    setLoading(false);
    setChatBusy(false);
  }

  useEffect(() => {
    if (!accessKey || !selectedReportId) return;
    const version = ++requestVersionRef.current;
    setDetail(null);
    setLoading(true);
    setError('');
    setChatHistory([]);
    setExpandedRowId(null);
    setStatusFilter('All results');
    setSearchQuery('');
    setChatBusy(false);

    apiFetch(`/reports/${encodeURIComponent(selectedReportId)}`)
      .then((res) => res.json())
      .then((data: Detail) => {
        if (version === requestVersionRef.current) {
          setDetail(data);
          setDraftAge(data.report.age_at_report ?? '');
          setDraftSex((data.report.sex_at_report as 'female' | 'male' | 'unknown') || 'unknown');
        }
      })
      .catch((err) => {
        if (version === requestVersionRef.current) {
          setError((err as Error).message);
        }
      })
      .finally(() => {
        if (version === requestVersionRef.current) {
          setLoading(false);
        }
      });
  }, [selectedReportId, accessKey]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ block: 'nearest' });
  }, [chatHistory]);

  async function handleUpload(file?: File) {
    if (!file) return;
    setError('');
    setNotice('');
    if (file.size > 8 * 1024 * 1024) {
      setError('Choose a file no larger than 8 MiB.');
      return;
    }
    setBusy(true);
    const version = requestVersionRef.current;
    try {
      const form = new FormData();
      form.append('file', file);
      const uploaded = await (await apiFetch('/reports/upload', { method: 'POST', body: form })).json();
      const reportList = await (await apiFetch('/reports')).json();
      if (version !== requestVersionRef.current) return;
      setReports(reportList.reports || []);
      setSelectedReportId(uploaded.report_id);
      setPage('Report Analysis');
      setNotice(
        uploaded.prompt_injection_detected
          ? 'Report imported. Untrusted instructions detected inside the document were neutralized and logged.'
          : 'Report imported and verified with source line citations.'
      );
    } catch (err) {
      if (version === requestVersionRef.current) {
        setError((err as Error).message);
      }
    } finally {
      setBusy(false);
      if (uploadInputRef.current) uploadInputRef.current.value = '';
    }
  }

  async function handleDownloadPdf() {
    if (!detail) return;
    setBusy(true);
    setError('');
    try {
      const response = await apiFetch(`/reports/${encodeURIComponent(detail.report.id)}/download`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `citylab-${detail.report.id}.pdf`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice('Verified PDF report downloaded.');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDemographicsUpdate(e: React.FormEvent) {
    e.preventDefault();
    if (!detail || busy) return;
    setError('');
    setNotice('');
    setBusy(true);
    const version = requestVersionRef.current;
    try {
      const updated: Detail = await (
        await apiFetch(`/reports/${encodeURIComponent(detail.report.id)}/demographics`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            age_at_report: draftAge.trim() === '' ? null : draftAge.trim(),
            sex_at_report: draftSex,
          }),
        })
      ).json();
      if (version === requestVersionRef.current) {
        setDetail(updated);
        setDraftAge(updated.report.age_at_report ?? '');
        setDraftSex((updated.report.sex_at_report as 'female' | 'male' | 'unknown') || 'unknown');
        setNotice('Patient demographics updated and rules engine re-evaluated.');
      }
    } catch (err) {
      if (version === requestVersionRef.current) {
        setError((err as Error).message);
      }
    } finally {
      if (version === requestVersionRef.current) {
        setBusy(false);
      }
    }
  }

  async function handleDemographicsReset() {
    if (!detail || busy) return;
    setError('');
    setNotice('');
    setBusy(true);
    const version = requestVersionRef.current;
    try {
      const updated: Detail = await (
        await apiFetch(`/reports/${encodeURIComponent(detail.report.id)}/demographics`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ age_at_report: null, sex_at_report: 'unknown' }),
        })
      ).json();
      if (version === requestVersionRef.current) {
        setDetail(updated);
        setDraftAge('');
        setDraftSex('unknown');
        setNotice('Demographics reset to missing/unknown; dependent ranges paused without guessing.');
      }
    } catch (err) {
      if (version === requestVersionRef.current) {
        setError((err as Error).message);
      }
    } finally {
      if (version === requestVersionRef.current) {
        setBusy(false);
      }
    }
  }

  async function handleAsk(e?: React.FormEvent, suggested?: string) {
    e?.preventDefault();
    const q = (suggested ?? question).trim();
    if (!q || !detail || chatBusy) return;
    const version = requestVersionRef.current;
    setQuestion('');
    setChatHistory((prev) => [...prev, { role: 'user', text: q }]);
    setChatBusy(true);
    try {
      const reply = await (
        await apiFetch(`/reports/${encodeURIComponent(detail.report.id)}/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ question: q }),
        })
      ).json();
      if (version === requestVersionRef.current) {
        setChatHistory((prev) => [
          ...prev,
          { role: 'assistant', text: reply.answer, mode: reply.mode, evidence_ids: reply.evidence_ids },
        ]);
      }
    } catch (err) {
      if (version === requestVersionRef.current) {
        setChatHistory((prev) => [
          ...prev,
          { role: 'assistant', text: (err as Error).message, mode: 'error' },
        ]);
      }
    } finally {
      if (version === requestVersionRef.current) {
        setChatBusy(false);
      }
    }
  }

  const results = detail?.analysis.results || [];
  const visibleResults = results.filter((r) => {
    const matchesStatus = statusFilter === 'All results' || r.status === statusFilter;
    const term = searchQuery.trim().toLowerCase();
    const matchesSearch =
      !term ||
      r.test.toLowerCase().includes(term) ||
      (r.canonical_test_name || '').toLowerCase().includes(term);
    return matchesStatus && matchesSearch;
  });

  const urgentWarnings = [...new Set(results.flatMap((r) => r.warnings))];

  function navigateTo(target: PageName) {
    setPage(target);
    setMobileMenuOpen(false);
  }

  if (!session) {
    return (
      <div className="grid min-h-screen bg-slate-50 lg:grid-cols-2">
        <div className="flex flex-col justify-between border-b border-slate-200 bg-white px-8 py-10 lg:border-b-0 lg:border-r lg:px-14 lg:py-12">
          <Brand />
          <div className="my-10 max-w-lg">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
              CityLab Clinical Report Explainer
            </div>
            <h1 className="mt-3 text-4xl font-bold tracking-tight text-slate-900 lg:text-5xl">
              Clear explanations. Verified evidence.
            </h1>
            <p className="mt-4 text-base leading-relaxed text-slate-600">
              Every test measurement is evaluated by a deterministic medical rules engine against documented CityLab
              reference intervals, unit conversions, and critical-value alerts.
            </p>
            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
                  <ShieldCheck size={16} className="text-teal-700" />
                  Patient-Scoped Isolation
                </div>
                <p className="mt-1.5 text-xs text-slate-600">
                  Bearer key authorization ensures strict single-patient access across dashboard, chat, and PDF exports.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
                  <Activity size={16} className="text-teal-700" />
                  Zero Guessing Policy
                </div>
                <p className="mt-1.5 text-xs text-slate-600">
                  Unsupported tests, missing units, duplicates, and missing demographics are explicitly flagged.
                </p>
              </div>
            </div>
          </div>
          <div className="text-xs text-slate-500">
            Tech Fusion &apos;26 · Problem Statement B — CityLab Diagnostics
          </div>
        </div>

        <main className="flex items-center justify-center px-6 py-12">
          <div className="w-full max-w-md space-y-6">
            <div className="rounded-xl border border-slate-200 bg-white p-7">
              <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-teal-200 bg-teal-50 text-teal-700">
                <LockKeyhole size={20} />
              </div>
              <h2 className="mt-5 text-xl font-bold text-slate-900">Open Patient Workspace</h2>
              <p className="mt-1.5 text-sm text-slate-600">
                Enter your patient access key, or select an isolated evaluation persona below.
              </p>

              <form onSubmit={handleLoginSubmit} className="mt-5 space-y-4">
                <div>
                  <label htmlFor="access-key" className="block text-xs font-semibold text-slate-700">
                    Patient Access Key
                  </label>
                  <input
                    id="access-key"
                    type="password"
                    autoComplete="off"
                    required
                    minLength={32}
                    value={draftKey}
                    onChange={(e) => setDraftKey(e.target.value)}
                    placeholder="Enter 32+ character patient access key"
                    className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400"
                  />
                </div>
                {error && (
                  <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                    {error}
                  </div>
                )}
                <button
                  type="submit"
                  disabled={busy}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-teal-700 px-4 py-2.5 text-sm font-semibold text-white hover:bg-teal-800"
                >
                  {busy ? <LoaderCircle size={16} className="spin" /> : <>Open Workspace <ArrowRight size={16} /></>}
                </button>
              </form>
            </div>

            {personas.length > 0 && (
              <div className="rounded-xl border border-slate-200 bg-white p-6">
                <div className="flex items-center justify-between">
                  <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                    Controlled Evaluation Sessions
                  </div>
                  <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                    Demo Mode
                  </span>
                </div>
                <div className="mt-3 space-y-2.5">
                  {personas.map((persona) => (
                    <button
                      key={persona.patient_id}
                      type="button"
                      disabled={busy}
                      onClick={() => authenticateWithToken(persona.token)}
                      className="flex w-full items-start justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 p-3 text-left hover:border-teal-600 hover:bg-white"
                    >
                      <div>
                        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                          <span>{persona.name}</span>
                          <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[10px] text-slate-600">
                            {persona.patient_id}
                          </span>
                        </div>
                        <div className="mt-0.5 text-xs font-medium text-teal-800">{persona.tag}</div>
                        <div className="mt-1 text-[11px] leading-snug text-slate-600">{persona.description}</div>
                      </div>
                      <ArrowRight size={15} className="mt-1 shrink-0 text-slate-400" />
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </main>
      </div>
    );
  }

  const resultsTable = (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
            Detailed Laboratory Results
            <span className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
              {results.length}
            </span>
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Click any row to inspect plain-language explanation, calculation trail, and verbatim source evidence.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <label className="flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs">
            <Search size={14} className="text-slate-400" />
            <input
              aria-label="Search tests"
              placeholder="Search test or alias..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-40 bg-transparent text-slate-800 outline-none placeholder:text-slate-400"
            />
          </label>
          <select
            aria-label="Filter classification"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-700"
          >
            <option>All results</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
              <th className="px-5 py-3">Test</th>
              <th className="px-4 py-3">Measured Value</th>
              <th className="px-4 py-3">Reference Interval</th>
              <th className="px-4 py-3">Classification</th>
              <th className="px-4 py-3 text-right">Evidence</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 text-sm">
            {visibleResults.map((r) => {
              const isOpen = expandedRowId === r.measurement_id;
              return (
                <React.Fragment key={r.measurement_id}>
                  <tr
                    className={`hover:bg-slate-50 ${isOpen ? 'bg-slate-50' : 'bg-white'}`}
                    onClick={() => setExpandedRowId(isOpen ? null : r.measurement_id)}
                  >
                    <td className="px-5 py-3.5 align-top">
                      <button
                        type="button"
                        aria-expanded={isOpen}
                        className="text-left font-semibold text-slate-900"
                      >
                        {r.test}
                        {r.canonical_test_name &&
                          r.canonical_test_name.toLowerCase() !== r.test.toLowerCase() && (
                            <span className="ml-2 rounded border border-teal-200 bg-teal-50 px-1.5 py-0.5 text-[10px] font-medium text-teal-800">
                              Alias → {r.canonical_test_name}
                            </span>
                          )}
                      </button>
                      <div className="mt-0.5 text-[11px] text-slate-500">
                        {r.evidence[0]?.file} · {r.evidence[0]?.location}
                      </div>
                    </td>

                    <td className="px-4 py-3.5 align-top">
                      <div className="numeric font-semibold text-slate-900">
                        {r.value || '—'}{' '}
                        <span className="text-xs font-normal text-slate-500">{r.unit || '(unit missing)'}</span>
                      </div>
                      {r.converted_value && r.converted_unit && (
                        <div className="numeric mt-1 inline-block rounded border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-700">
                          Converted: {r.converted_value} {r.converted_unit}
                        </div>
                      )}
                    </td>

                    <td className="numeric px-4 py-3.5 align-top text-xs text-slate-600">{r.reference}</td>

                    <td className="px-4 py-3.5 align-top">
                      <span
                        className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 text-xs font-medium ${
                          STATUS_BADGE_CLASS[r.status]
                        }`}
                      >
                        <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT_CLASS[r.status]}`} />
                        {displayStatus(r.status)}
                      </span>
                    </td>

                    <td className="px-4 py-3.5 text-right align-top">
                      <button
                        type="button"
                        aria-label={`Inspect evidence for ${r.test}`}
                        aria-expanded={isOpen}
                        className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                      >
                        {isOpen ? (
                          <>
                            Hide <ChevronDown size={14} />
                          </>
                        ) : (
                          <>
                            Inspect <ChevronRight size={14} />
                          </>
                        )}
                      </button>
                    </td>
                  </tr>
                  {isOpen && (
                    <tr>
                      <td colSpan={5} className="p-0">
                        <EvidenceDrawer result={r} />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>

        {visibleResults.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center text-slate-500">
            <Search size={22} className="text-slate-400" />
            <div className="mt-2 text-sm font-semibold text-slate-700">No matching tests</div>
            <p className="mt-1 text-xs">Clear the search query or switch classification filters.</p>
          </div>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 bg-slate-50 px-5 py-3 text-[11px] text-slate-500">
        <span>
          Showing {visibleResults.length} of {results.length} measurements
        </span>
        <span className="flex items-center gap-1.5">
          <ShieldCheck size={14} className="text-teal-700" />
          All classifications computed deterministically by CityLab Rules Engine
        </span>
      </div>
    </section>
  );

  return (
    <div className="flex min-h-screen bg-slate-50 text-slate-900">
      <aside
        className={`fixed inset-y-0 left-0 z-30 flex w-64 flex-col border-r border-slate-200 bg-white px-4 py-6 transition-transform lg:translate-x-0 ${
          mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="px-2">
          <Brand />
        </div>

        <div className="mt-7 px-3 text-[10px] font-bold uppercase tracking-[0.14em] text-slate-400">
          Clinical Workspace
        </div>
        <nav aria-label="Main navigation" className="mt-2 flex-1 space-y-1">
          {NAVIGATION.map(({ name, icon: Icon }) => {
            const active = page === name;
            return (
              <button
                key={name}
                type="button"
                onClick={() => navigateTo(name)}
                className={`flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm font-medium ${
                  active
                    ? 'border border-teal-200 bg-teal-50 font-semibold text-teal-800'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`}
              >
                <Icon size={17} />
                <span className="flex-1">{name}</span>
                {active && <span className="h-1.5 w-1.5 rounded-full bg-teal-700" />}
              </button>
            );
          })}
        </nav>

        <div className="space-y-3 border-t border-slate-200 pt-4">
          {personas.length > 0 && (
            <div>
              <label className="block px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                Switch Evaluation Patient
              </label>
              <select
                aria-label="Switch evaluation patient"
                value={session.patient.id}
                onChange={(e) => {
                  const chosen = personas.find((p) => p.patient_id === e.target.value);
                  if (chosen) authenticateWithToken(chosen.token);
                }}
                className="mt-1.5 w-full rounded-md border border-slate-300 bg-slate-50 px-2.5 py-2 text-xs font-medium text-slate-800"
              >
                {personas.map((p) => (
                  <option key={p.patient_id} value={p.patient_id}>
                    {p.name} ({p.patient_id})
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
              <ShieldCheck size={15} className="text-teal-700" />
              Strict Patient Isolation
            </div>
            <p className="mt-1 text-[11px] leading-snug text-slate-600">
              Authorized for <span className="font-mono font-semibold">{session.patient.id}</span> only.
            </p>
          </div>

          <button
            type="button"
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
          >
            <LogOut size={15} />
            Sign Out
          </button>
        </div>
      </aside>

      {mobileMenuOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={() => setMobileMenuOpen(false)}
          className="fixed inset-0 z-20 bg-slate-900/40 lg:hidden"
        />
      )}

      <div className="flex flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-8">
          <div className="flex items-center gap-3">
            <button
              type="button"
              aria-label="Open navigation"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-md border border-slate-200 p-2 text-slate-600 lg:hidden"
            >
              <Menu size={18} />
            </button>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>Workspace</span>
              <ChevronRight size={14} />
              <strong className="font-semibold text-slate-900">{page}</strong>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-1.5 rounded border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-medium text-slate-600 sm:inline-flex">
              <LockKeyhole size={12} className="text-teal-700" />
              Corpus v{session.knowledge_version.slice(0, 8)}
            </span>
            <div className="flex items-center gap-2">
              <span className="grid h-8 w-8 place-items-center rounded-full border border-slate-200 bg-slate-100 text-xs font-semibold text-slate-700">
                {session.patient.name.slice(0, 1)}
              </span>
              <span className="hidden text-xs font-semibold text-slate-800 sm:inline">{session.patient.name}</span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl flex-1 space-y-6 px-4 py-7 sm:px-8">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-teal-700">
                CityLab Diagnostics
              </div>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                {page === 'Dashboard' ? 'Patient Laboratory Analysis' : page}
              </h1>
              <p className="mt-1 text-sm text-slate-600">
                {page === 'AI Assistant'
                  ? 'Ask questions grounded strictly in your verified results and CityLab glossary.'
                  : 'Inspect measurements, unit conversions, reference intervals, and clinical evidence.'}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <input
                ref={uploadInputRef}
                type="file"
                className="hidden"
                accept=".txt,.md,.csv,.json,.pdf"
                aria-label="Upload a report"
                onChange={(e) => handleUpload(e.target.files?.[0])}
              />
              <button
                type="button"
                disabled={busy}
                onClick={() => uploadInputRef.current?.click()}
                className="inline-flex items-center gap-2 rounded-md border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
              >
                <Upload size={15} />
                Upload Report
              </button>
              <button
                type="button"
                disabled={!detail || busy}
                onClick={handleDownloadPdf}
                className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-3.5 py-2 text-xs font-semibold text-white hover:bg-teal-800"
              >
                {busy ? <LoaderCircle size={15} className="spin" /> : <Download size={15} />}
                Download PDF
              </button>
            </div>
          </div>

          {error && (
            <div
              role="alert"
              className="flex items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-xs text-red-900"
            >
              <div className="flex items-center gap-2.5">
                <AlertTriangle size={16} className="shrink-0 text-red-700" />
                <span>{error}</span>
              </div>
              <button type="button" onClick={() => setError('')} aria-label="Dismiss error">
                <X size={15} />
              </button>
            </div>
          )}

          {notice && (
            <div
              role="status"
              className="flex items-center justify-between gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs text-emerald-900"
            >
              <div className="flex items-center gap-2.5">
                <Check size={16} className="shrink-0 text-emerald-700" />
                <span>{notice}</span>
              </div>
              <button type="button" onClick={() => setNotice('')} aria-label="Dismiss notification">
                <X size={15} />
              </button>
            </div>
          )}

          {/* Patient Strip & Report Selector */}
          <section className="grid gap-4 rounded-lg border border-slate-200 bg-white p-5 md:grid-cols-12 md:items-center">
            <div className="flex items-center gap-3.5 md:col-span-4">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-slate-200 bg-slate-100 text-sm font-bold text-slate-700">
                <UserCheck size={18} />
              </div>
              <div>
                <div className="text-sm font-bold text-slate-900">{session.patient.name}</div>
                <div className="mt-0.5 font-mono text-xs text-slate-500">ID: {session.patient.id}</div>
              </div>
            </div>

            <div className="flex flex-wrap gap-6 border-t border-slate-200 pt-3 md:col-span-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Age at Report</div>
                <div className="mt-0.5 text-sm font-semibold text-slate-800">
                  {detail?.report.age_at_report ? (
                    `${detail.report.age_at_report} yrs`
                  ) : (
                    <span className="text-amber-700">Missing (not provided)</span>
                  )}
                </div>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  Biological Sex
                </div>
                <div className="mt-0.5 text-sm font-semibold capitalize text-slate-800">
                  {detail?.report.sex_at_report === 'unknown' ? (
                    <span className="text-amber-700">Unknown</span>
                  ) : (
                    detail?.report.sex_at_report || 'Unknown'
                  )}
                </div>
              </div>
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Report Date</div>
                <div className="mt-0.5 text-sm font-semibold text-slate-800">
                  {formatDate(detail?.report.report_date ?? null)}
                </div>
              </div>
            </div>

            <div className="border-t border-slate-200 pt-3 md:col-span-4 md:border-t-0 md:pt-0">
              <label className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Select Authorized Report
              </label>
              <select
                aria-label="Select report"
                value={selectedReportId}
                disabled={!reports.length}
                onChange={(e) => setSelectedReportId(e.target.value)}
                className="mt-1 w-full rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-800"
              >
                {!reports.length && <option>No reports available</option>}
                {reports.map((r) => (
                  <option key={r.id} value={r.id}>
                    {formatDate(r.report_date)} · {r.source_file || r.id.slice(0, 14)} ({r.tests} tests)
                  </option>
                ))}
              </select>
            </div>
          </section>

          {detail &&
            (detail.report.age_at_report === null ||
              detail.report.sex_at_report === 'unknown' ||
              detail.report.issues.some((i) => i.startsWith('Demographics updated via session:'))) && (
              <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <form
                  onSubmit={handleDemographicsUpdate}
                  className="flex flex-wrap items-end justify-between gap-4"
                >
                  <div className="max-w-xl">
                    <div className="text-xs font-bold text-amber-950">
                      {detail.report.age_at_report === null || detail.report.sex_at_report === 'unknown'
                        ? 'Missing Patient Demographics — No Defaults Assumed'
                        : 'Session Demographics Applied'}
                    </div>
                    <p className="mt-0.5 text-xs text-amber-900">
                      {detail.report.age_at_report === null || detail.report.sex_at_report === 'unknown'
                        ? 'Age- or sex-dependent tests remain Cannot Be Classified until verified demographics are provided.'
                        : 'Demographics were supplied for this authorized session. You can update them or reset to missing.'}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-end gap-3">
                    <div>
                      <label htmlFor="demo-age-input" className="block text-[10px] font-semibold uppercase text-amber-900">
                        Age (years)
                      </label>
                      <input
                        id="demo-age-input"
                        type="number"
                        min={0}
                        max={150}
                        step="1"
                        placeholder="e.g. 34"
                        value={draftAge}
                        onChange={(e) => setDraftAge(e.target.value)}
                        className="mt-1 w-24 rounded-md border border-amber-300 bg-white px-2.5 py-1.5 text-xs text-slate-900"
                      />
                    </div>
                    <div>
                      <label htmlFor="demo-sex-select" className="block text-[10px] font-semibold uppercase text-amber-900">
                        Biological Sex
                      </label>
                      <select
                        id="demo-sex-select"
                        value={draftSex}
                        onChange={(e) => setDraftSex(e.target.value as 'female' | 'male' | 'unknown')}
                        className="mt-1 rounded-md border border-amber-300 bg-white px-2.5 py-1.5 text-xs text-slate-900"
                      >
                        <option value="unknown">unknown</option>
                        <option value="female">female</option>
                        <option value="male">male</option>
                      </select>
                    </div>
                    <button
                      type="submit"
                      disabled={busy}
                      className="rounded-md bg-teal-700 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-teal-800"
                    >
                      Apply &amp; Re-Analyze
                    </button>
                    {detail.report.issues.some((i) => i.startsWith('Demographics updated via session:')) && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={handleDemographicsReset}
                        className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
                      >
                        Reset to Missing
                      </button>
                    )}
                  </div>
                </form>
              </section>
            )}

          {loading ? (
            <div role="status" className="flex flex-col items-center justify-center rounded-lg border border-slate-200 bg-white py-16">
              <LoaderCircle size={26} className="spin text-teal-700" />
              <div className="mt-3 text-sm font-semibold text-slate-800">Analyzing Report &amp; Verifying Rules</div>
              <p className="mt-1 text-xs text-slate-500">Loading measurements and CityLab source evidence.</p>
            </div>
          ) : !detail ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-slate-200 bg-white px-6 py-16 text-center">
              <FileText size={32} className="text-slate-400" />
              <h2 className="mt-3 text-base font-semibold text-slate-900">
                {reports.length ? 'Select a report above' : 'No laboratory reports on file'}
              </h2>
              <p className="mt-1 max-w-md text-xs text-slate-500">
                Upload a CityLab report in TXT, Markdown, CSV, JSON, or text PDF format containing a Test, Value, Unit table.
              </p>
            </div>
          ) : page === 'Patient Reports' ? (
            <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
                <div>
                  <h2 className="text-base font-semibold text-slate-900">Authorized Patient Reports</h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Only records belonging to {session.patient.name} ({session.patient.id}) are accessible.
                  </p>
                </div>
              </div>
              <div className="divide-y divide-slate-200">
                {reports.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => {
                      setSelectedReportId(r.id);
                      navigateTo('Report Analysis');
                    }}
                    className="flex w-full items-center justify-between gap-4 px-6 py-4 text-left hover:bg-slate-50"
                  >
                    <div className="flex items-center gap-3.5">
                      <span className="grid h-9 w-9 place-items-center rounded-md border border-teal-200 bg-teal-50 text-teal-700">
                        <FileText size={17} />
                      </span>
                      <div>
                        <div className="text-sm font-semibold text-slate-900">
                          {formatDate(r.report_date)} — {r.source_file || r.id}
                        </div>
                        <div className="mt-0.5 text-xs text-slate-500">
                          {r.tests} measurements · {r.noise_lines_skipped ?? 0} noise lines filtered
                          {r.prompt_injection_detected ? ' · Untrusted prompt-injection neutralized' : ''}
                        </div>
                      </div>
                    </div>
                    <ChevronRight size={17} className="text-slate-400" />
                  </button>
                ))}
              </div>
              <div className="border-t border-slate-200 bg-slate-50 p-6">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-700">
                  Supported Upload Format
                </h3>
                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                  Include <code className="rounded bg-slate-200 px-1 py-0.5">Patient ID: {session.patient.id}</code>,
                  optional <code className="rounded bg-slate-200 px-1 py-0.5">Report Date: YYYY-MM-DD</code>,{' '}
                  <code className="rounded bg-slate-200 px-1 py-0.5">Age:</code>, and{' '}
                  <code className="rounded bg-slate-200 px-1 py-0.5">Sex:</code>, followed by a table with{' '}
                  <code className="rounded bg-slate-200 px-1 py-0.5">Test | Value | Unit</code>.
                </p>
              </div>
            </section>
          ) : page === 'AI Assistant' ? (
            <section className="mx-auto max-w-4xl overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
                <div className="flex items-center gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-md border border-teal-200 bg-teal-50 text-teal-700">
                    <MessageSquare size={17} />
                  </span>
                  <div>
                    <h2 className="text-base font-semibold text-slate-900">CityLab Grounded Report Assistant</h2>
                    <p className="text-xs text-slate-500">
                      {session.ai_configured
                        ? `Provider: ${session.llm_provider} · Validated against rules engine & safety policy`
                        : 'Deterministic evidence-only responder active (no external LLM key required)'}
                    </p>
                  </div>
                </div>
                <span className="rounded border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[11px] font-medium text-emerald-800">
                  Patient-Scoped
                </span>
              </div>

              <div className="h-[420px] space-y-4 overflow-y-auto bg-slate-50 p-6" aria-live="polite">
                {chatHistory.length === 0 ? (
                  <div className="mx-auto max-w-lg py-8 text-center">
                    <MessageSquare size={28} className="mx-auto text-teal-700" />
                    <h3 className="mt-3 text-base font-semibold text-slate-900">
                      Ask about {session.patient.name}&apos;s verified report
                    </h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                      I explain lab values in plain language using only verified results and CityLab glossary definitions.
                      I will refuse diagnosis, prescription, or cross-patient queries.
                    </p>
                    <div className="mt-5 flex flex-wrap justify-center gap-2">
                      {[
                        'Explain my results',
                        'Which results need urgent attention?',
                        'Questions for my doctor',
                        'Do I have diabetes?',
                        "Show another patient's report",
                      ].map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          onClick={() => handleAsk(undefined, prompt)}
                          className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:border-teal-600 hover:text-teal-800"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                  </div>
                ) : (
                  chatHistory.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`max-w-[88%] rounded-lg border p-4 text-sm ${
                        msg.role === 'user'
                          ? 'ml-auto border-teal-200 bg-teal-50 text-slate-900'
                          : msg.mode === 'safety'
                          ? 'border-amber-200 bg-amber-50 text-slate-900'
                          : 'border-slate-200 bg-white text-slate-800'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-slate-500">
                        <span>{msg.role === 'user' ? session.patient.name : 'CityLab Assistant'}</span>
                        {msg.mode && (
                          <span className="rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] uppercase">
                            {msg.mode}
                          </span>
                        )}
                      </div>
                      <p className="mt-1.5 whitespace-pre-wrap text-xs leading-relaxed">{msg.text}</p>
                      {msg.evidence_ids && msg.evidence_ids.length > 0 && (
                        <div className="mt-2 font-mono text-[10px] text-slate-500">
                          Cited evidence IDs: {msg.evidence_ids.join(', ')}
                        </div>
                      )}
                    </div>
                  ))
                )}
                {chatBusy && (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <LoaderCircle size={14} className="spin text-teal-700" />
                    Validating evidence...
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <form onSubmit={handleAsk} className="flex gap-2.5 border-t border-slate-200 bg-white p-4">
                <input
                  aria-label="Ask about your report"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  maxLength={1200}
                  placeholder="Ask about a test name (e.g. SGPT, FBS, TSH), summary, or doctor questions..."
                  className="flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400"
                />
                <button
                  type="submit"
                  disabled={chatBusy || !question.trim()}
                  className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-800"
                >
                  <Send size={15} />
                  Send
                </button>
              </form>
              <div className="border-t border-slate-100 bg-slate-50 px-4 py-2 text-center text-[11px] text-slate-500">
                {detail.analysis.disclaimer}
              </div>
            </section>
          ) : page === 'Report Downloads' ? (
            <section className="grid gap-8 rounded-lg border border-slate-200 bg-white p-8 md:grid-cols-12 md:items-center">
              <div className="md:col-span-4">
                <div className="mx-auto flex h-56 w-44 flex-col justify-between rounded-lg border border-slate-200 bg-slate-50 p-5">
                  <div className="flex items-center justify-between text-teal-700">
                    <FlaskConical size={22} />
                    <span className="text-[10px] font-bold tracking-widest text-slate-500">PDF</span>
                  </div>
                  <div className="space-y-2">
                    <div className="text-xs font-bold text-slate-800">CityLab Diagnostics</div>
                    <div className="h-1.5 w-full rounded bg-slate-200" />
                    <div className="h-1.5 w-5/6 rounded bg-slate-200" />
                    <div className="h-1.5 w-2/3 rounded bg-slate-200" />
                  </div>
                  <div className="text-[10px] font-mono text-slate-500">{detail.report.id.slice(0, 14)}</div>
                </div>
              </div>
              <div className="space-y-4 md:col-span-8">
                <div className="text-xs font-semibold uppercase tracking-wider text-teal-700">
                  Server-Generated Clinical Summary PDF
                </div>
                <h2 className="text-2xl font-bold text-slate-900">Download Verified Patient Report</h2>
                <p className="text-sm text-slate-600">
                  Generates a clean, flat-formatted multi-page PDF directly from the verified rules-engine analysis for{' '}
                  <strong>{session.patient.name}</strong>.
                </p>
                <ul className="grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Patient demographics &amp; report dates
                  </li>
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Classification summary counts
                  </li>
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Unit conversions &amp; reference intervals
                  </li>
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Urgent alerts &amp; doctor questions
                  </li>
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Verbatim source file &amp; line citations
                  </li>
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Missing data &amp; non-diagnosis disclaimer
                  </li>
                </ul>
                <div className="pt-2">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={handleDownloadPdf}
                    className="inline-flex items-center gap-2 rounded-md bg-teal-700 px-5 py-2.5 text-sm font-semibold text-white hover:bg-teal-800"
                  >
                    {busy ? <LoaderCircle size={16} className="spin" /> : <Download size={16} />}
                    Download PDF Report
                  </button>
                </div>
              </div>
            </section>
          ) : (
            <>
              {/* Summary Metric Cards */}
              <section aria-label="Result counts" className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
                <button
                  type="button"
                  onClick={() => setStatusFilter('All results')}
                  className={`rounded-lg border p-4 text-left ${
                    statusFilter === 'All results'
                      ? 'border-teal-700 bg-teal-50'
                      : 'border-slate-200 bg-white hover:border-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between text-xs font-medium text-slate-600">
                    <span>Total Tests</span>
                    <FileText size={14} className="text-teal-700" />
                  </div>
                  <div className="numeric mt-2 text-2xl font-bold text-slate-900">{results.length}</div>
                  <div className="mt-1 text-[11px] text-slate-500">Extracted rows</div>
                </button>

                {STATUSES.map((s) => {
                  const selected = statusFilter === s;
                  return (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStatusFilter(selected ? 'All results' : s)}
                      className={`rounded-lg border p-4 text-left ${
                        selected ? 'border-teal-700 bg-teal-50' : 'border-slate-200 bg-white hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs font-medium text-slate-600">
                        <span>{displayStatus(s)}</span>
                        <span className={`h-2 w-2 rounded-full ${STATUS_DOT_CLASS[s]}`} />
                      </div>
                      <div className="numeric mt-2 text-2xl font-bold text-slate-900">
                        {detail.analysis.counts[s] ?? 0}
                      </div>
                      <div className="mt-1 text-[11px] text-slate-500">
                        {s === 'Urgent'
                          ? 'Immediate review'
                          : s === 'Cannot Be Classified'
                          ? 'Needs review/data'
                          : s === 'Normal'
                          ? 'In reference range'
                          : 'Out of interval'}
                      </div>
                    </button>
                  );
                })}
              </section>

              {/* Urgent Warnings Banner */}
              {urgentWarnings.length > 0 && (
                <section
                  role="alert"
                  className="rounded-lg border border-red-300 bg-red-50 px-5 py-4 text-red-900"
                >
                  <div className="flex items-start gap-3">
                    <ShieldAlert size={20} className="mt-0.5 shrink-0 text-red-700" />
                    <div className="space-y-1.5">
                      <div className="text-sm font-bold text-red-950">
                        Urgent Clinical Attention Required
                      </div>
                      {urgentWarnings.map((w) => (
                        <p key={w} className="text-xs leading-relaxed text-red-900">
                          {w}
                        </p>
                      ))}
                    </div>
                  </div>
                </section>
              )}

              {/* Main Analysis Grid */}
              <div className="grid gap-6 xl:grid-cols-12">
                <div className="space-y-5 xl:col-span-8">
                  {resultsTable}

                  {/* Extraction & Security Telemetry */}
                  {(detail.metadata || detail.report.issues.length > 0) && (
                    <section className="rounded-lg border border-slate-200 bg-white p-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold text-slate-900">
                          Extraction &amp; Document Security Telemetry
                        </h3>
                        {detail.metadata?.prompt_injection_detected && (
                          <span className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-900">
                            Prompt-Injection Attempt Neutralized
                          </span>
                        )}
                      </div>
                      <div className="mt-3 grid gap-3 text-xs text-slate-600 sm:grid-cols-3">
                        <div className="rounded border border-slate-200 bg-slate-50 p-3">
                          <div className="text-[10px] font-semibold uppercase text-slate-400">Source File</div>
                          <div className="mt-1 truncate font-mono text-slate-800">
                            {detail.metadata?.source_file || detail.report.source_file || 'Uploaded'}
                          </div>
                        </div>
                        <div className="rounded border border-slate-200 bg-slate-50 p-3">
                          <div className="text-[10px] font-semibold uppercase text-slate-400">Lines Scanned</div>
                          <div className="numeric mt-1 font-semibold text-slate-800">
                            {detail.metadata?.line_count ?? '—'} total
                          </div>
                        </div>
                        <div className="rounded border border-slate-200 bg-slate-50 p-3">
                          <div className="text-[10px] font-semibold uppercase text-slate-400">Boilerplate Skipped</div>
                          <div className="numeric mt-1 font-semibold text-slate-800">
                            {detail.metadata?.noise_lines_skipped ?? 0} non-result lines
                          </div>
                        </div>
                      </div>
                      {detail.report.issues.length > 0 && (
                        <ul className="mt-3 space-y-1 text-xs text-slate-600">
                          {detail.report.issues.map((issue, idx) => (
                            <li key={idx} className="font-mono text-[11px]">
                              • {issue}
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                  )}

                  <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
                    <ShieldCheck size={16} className="mt-0.5 shrink-0 text-teal-700" />
                    <p>{detail.analysis.disclaimer}</p>
                  </div>
                </div>

                <aside className="space-y-5 xl:col-span-4">
                  {/* Questions for your doctor */}
                  <section className="rounded-lg border border-slate-200 bg-white p-5">
                    <div className="flex items-center gap-2.5">
                      <span className="grid h-8 w-8 place-items-center rounded-md border border-teal-200 bg-teal-50 text-teal-700">
                        <ClipboardList size={16} />
                      </span>
                      <div>
                        <h2 className="text-sm font-bold text-slate-900">Questions for Your Doctor</h2>
                        <p className="text-[11px] text-slate-500">Generated from verified findings</p>
                      </div>
                    </div>
                    <ol className="mt-4 divide-y divide-slate-100">
                      {detail.analysis.doctor_questions.map((q, idx) => (
                        <li key={idx} className="flex gap-3 py-3 text-xs leading-relaxed text-slate-700 first:pt-1 last:pb-0">
                          <span className="numeric font-mono text-[11px] font-semibold text-teal-700">
                            {String(idx + 1).padStart(2, '0')}
                          </span>
                          <span>{q}</span>
                        </li>
                      ))}
                    </ol>
                  </section>

                  {/* Assistant Shortcut Card */}
                  <section className="rounded-lg border border-teal-200 bg-teal-50 p-5">
                    <div className="flex items-center gap-2 text-sm font-bold text-teal-900">
                      <MessageSquare size={17} />
                      Ask the Grounded Assistant
                    </div>
                    <p className="mt-1.5 text-xs leading-relaxed text-teal-800">
                      Need a simpler explanation of any measurement, conversion, or why a test could not be classified?
                    </p>
                    <button
                      type="button"
                      onClick={() => navigateTo('AI Assistant')}
                      className="mt-4 inline-flex w-full items-center justify-between rounded-md bg-teal-700 px-3.5 py-2 text-xs font-semibold text-white hover:bg-teal-800"
                    >
                      <span>Open AI Assistant</span>
                      <ArrowRight size={15} />
                    </button>
                  </section>
                </aside>
              </div>
            </>
          )}

          <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-5 text-[11px] text-slate-500">
            <span>CityLab Diagnostics · Evidence-First Report Explainer (JSON Storage Prototype)</span>
            <span>Tech Fusion &apos;26 Hackathon</span>
          </footer>
        </main>
      </div>
    </div>
  );
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
