import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  RefreshCw,
  Search,
  Send,
  ShieldAlert,
  ShieldCheck,
  Upload,
  UserCheck,
  X,
} from 'lucide-react';
import type { ChatMessage, DemoPersona, Detail, ReportSummary, Result, Session, Status } from './types';
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
  { name: 'Report assistant', icon: MessageSquare },
  { name: 'Report Downloads', icon: Download },
] as const;

type PageName = (typeof NAVIGATION)[number]['name'];
type DemoState = 'loading' | 'enabled' | 'disabled' | 'error';

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
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg border border-teal-200 bg-teal-50 text-teal-700">
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
    <div className="border-b border-slate-200 bg-slate-50 px-5 py-5 text-slate-700 sm:px-6">
      <div className="grid gap-5 lg:grid-cols-2">
        <div className="min-w-0 space-y-4">
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
                Calculation &amp; Rule Trace
              </div>
              <ul className="mt-2 space-y-1.5 text-xs text-slate-700">
                {result.audit.map((step, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-teal-700" />
                    <span className="break-words font-mono text-[11px] leading-relaxed">{step}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="min-w-0">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
            View sources ({result.evidence.length})
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
  const [demoState, setDemoState] = useState<DemoState>('loading');
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
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
  const [activeMeasurementIds, setActiveMeasurementIds] = useState<string[]>([]);
  const [analysisRevision, setAnalysisRevision] = useState<string>('');
  const [chatBusy, setChatBusy] = useState(false);

  const [draftAge, setDraftAge] = useState('');
  const [draftSex, setDraftSex] = useState<'female' | 'male' | 'unknown'>('unknown');

  const uploadInputRef = useRef<HTMLInputElement>(null);
  const requestVersionRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadDemoSessions = useCallback(() => {
    setDemoState('loading');
    fetch('/api/demo/sessions')
      .then((res) => {
        if (!res.ok) throw new Error('Failed to load sample reports');
        return res.json();
      })
      .then((data) => {
        if (data?.enabled && Array.isArray(data.personas) && data.personas.length > 0) {
          setPersonas(data.personas);
          setDemoState('enabled');
        } else {
          setPersonas([]);
          setDemoState('disabled');
        }
      })
      .catch(() => {
        setPersonas([]);
        setDemoState('error');
      });
  }, []);

  useEffect(() => {
    loadDemoSessions();
  }, [loadDemoSessions]);

  async function apiFetch(path: string, init: RequestInit = {}, tokenOverride = accessKey, signal?: AbortSignal) {
    const response = await fetch(`/api${path}`, {
      ...init,
      signal,
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

  function resetPatientWorkspaceState() {
    abortRef.current?.abort();
    const nextController = new AbortController();
    abortRef.current = nextController;
    const version = ++requestVersionRef.current;

    setDetail(null);
    setReports([]);
    setSelectedReportId('');
    setChatHistory([]);
    setActiveMeasurementIds([]);
    setAnalysisRevision('');
    setExpandedRowId(null);
    setStatusFilter('All results');
    setSearchQuery('');
    setQuestion('');
    setError('');
    setNotice('');
    setChatBusy(false);
    return { controller: nextController, version };
  }

  async function authenticateWithToken(tokenToUse: string) {
    if (!tokenToUse) return;
    const { controller, version } = resetPatientWorkspaceState();
    setBusy(true);
    try {
      const currentSession: Session = await (
        await apiFetch('/session', {}, tokenToUse, controller.signal)
      ).json();
      const reportList = await (await apiFetch('/reports', {}, tokenToUse, controller.signal)).json();
      if (version !== requestVersionRef.current) return;
      setAccessKey(tokenToUse);
      setDraftKey('');
      setSession(currentSession);
      setReports(reportList.reports || []);
      setSelectedReportId(reportList.reports?.[0]?.id || '');
      setPage('Dashboard');
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      if (version === requestVersionRef.current) {
        setError((err as Error).message);
      }
    } finally {
      if (version === requestVersionRef.current) {
        setBusy(false);
      }
    }
  }

  function handleLoginSubmit(e: React.FormEvent) {
    e.preventDefault();
    authenticateWithToken(draftKey.trim());
  }

  function logout() {
    resetPatientWorkspaceState();
    setAccessKey('');
    setSession(null);
    setDraftKey('');
    setPage('Dashboard');
    setBusy(false);
    setLoading(false);
  }

  useEffect(() => {
    if (!accessKey || !selectedReportId) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const version = ++requestVersionRef.current;

    setDetail(null);
    setLoading(true);
    setError('');
    setChatHistory([]);
    setActiveMeasurementIds([]);
    setAnalysisRevision('');
    setExpandedRowId(null);
    setStatusFilter('All results');
    setSearchQuery('');
    setChatBusy(false);

    apiFetch(`/reports/${encodeURIComponent(selectedReportId)}`, {}, accessKey, controller.signal)
      .then((res) => res.json())
      .then((data: Detail) => {
        if (version === requestVersionRef.current) {
          setDetail(data);
          setAnalysisRevision(data.analysis_revision || '');
          setDraftAge(data.report.age_at_report ?? '');
          setDraftSex((data.report.sex_at_report as 'female' | 'male' | 'unknown') || 'unknown');
        }
      })
      .catch((err) => {
        if ((err as Error).name === 'AbortError') return;
        if (version === requestVersionRef.current) {
          setError((err as Error).message);
        }
      })
      .finally(() => {
        if (version === requestVersionRef.current) {
          setLoading(false);
        }
      });

    return () => {
      controller.abort();
    };
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
        session?.knowledge_provenance === 'synthetic'
          ? 'Report imported. Under synthetic demonstration mode, uploaded real reports remain unclassified unless reviewed clinical rules are loaded.'
          : uploaded.prompt_injection_detected
          ? 'Report imported. Document instructions were neutralized and ignored.'
          : 'Report imported with source line references.'
      );
    } catch (err) {
      if (version === requestVersionRef.current) {
        setError((err as Error).message);
      }
    } finally {
      if (version === requestVersionRef.current) {
        setBusy(false);
      }
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
      setNotice('PDF report downloaded.');
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
        setAnalysisRevision(updated.analysis_revision || '');
        setChatHistory([]);
        setActiveMeasurementIds([]);
        setDraftAge(updated.report.age_at_report ?? '');
        setDraftSex((updated.report.sex_at_report as 'female' | 'male' | 'unknown') || 'unknown');
        setNotice('Patient information updated and results recalculated. Assistant context has been refreshed.');
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
        setAnalysisRevision(updated.analysis_revision || '');
        setChatHistory([]);
        setActiveMeasurementIds([]);
        setDraftAge('');
        setDraftSex('unknown');
        setNotice('Restored missing patient information; dependent ranges were paused without guessing.');
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
    const controller = abortRef.current;
    setQuestion('');
    setChatHistory((prev) => [...prev, { role: 'user', text: q }]);
    setChatBusy(true);
    try {
      const reply = await (
        await apiFetch(
          `/reports/${encodeURIComponent(detail.report.id)}/chat`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              question: q,
              active_measurement_ids: activeMeasurementIds,
              context_revision: analysisRevision || detail.analysis_revision || '',
            }),
          },
          accessKey,
          controller?.signal
        )
      ).json();
      if (version === requestVersionRef.current) {
        setActiveMeasurementIds(Array.isArray(reply.active_measurement_ids) ? reply.active_measurement_ids : []);
        if (reply.analysis_revision) {
          setAnalysisRevision(reply.analysis_revision);
        }
        setChatHistory((prev) => [
          ...prev,
          {
            role: 'assistant',
            text: reply.answer,
            ai_used: Boolean(reply.ai_used),
            sources: Array.isArray(reply.sources) ? reply.sources : [],
            report_urgent_notice: reply.report_urgent_notice || null,
          },
        ]);
      }
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      if (version === requestVersionRef.current) {
        setChatHistory((prev) => [
          ...prev,
          { role: 'assistant', text: (err as Error).message, ai_used: false },
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
  const isSyntheticContext = Boolean(
    session?.synthetic_demo ||
      session?.knowledge_provenance === 'synthetic' ||
      detail?.report.synthetic ||
      detail?.analysis.knowledge_provenance === 'synthetic'
  );

  function navigateTo(target: PageName) {
    setPage(target);
    setMobileMenuOpen(false);
  }

  if (!session) {
    return (
      <div className="grid min-h-screen bg-slate-50 lg:grid-cols-2">
        <div className="flex flex-col justify-between border-b border-slate-200 bg-white px-6 py-8 lg:border-b-0 lg:border-r lg:px-14 lg:py-12">
          <Brand />
          <div className="my-8 max-w-lg">
            <div className="text-xs font-semibold uppercase tracking-[0.16em] text-teal-700">
              CityLab Diagnostics
            </div>
            <h1 className="mt-3 text-3xl font-bold tracking-tight text-slate-900 lg:text-4xl">
              Clear lab explanations backed by traceable rules.
            </h1>
            <p className="mt-4 text-sm leading-relaxed text-slate-600 sm:text-base">
              Inspect test values, reference limits, unit conversions, urgent alerts, and plain-language explanations
              without guesswork.
            </p>
            <div className="mt-8 grid gap-3 sm:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
                  <ShieldCheck size={16} className="text-teal-700" />
                  Single-Patient Isolation
                </div>
                <p className="mt-1.5 text-xs text-slate-600">
                  Each report session strictly limits access to that patient&apos;s records, questions, and PDF export.
                </p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center gap-2 text-xs font-semibold text-slate-900">
                  <Activity size={16} className="text-teal-700" />
                  Zero Guessing Policy
                </div>
                <p className="mt-1.5 text-xs text-slate-600">
                  Missing age/sex, missing units, unsupported assays, and repeated measurements stay explicitly flagged.
                </p>
              </div>
            </div>
          </div>
          <div className="text-xs text-slate-500">
            Tech Fusion &apos;26 · CityLab Report Explainer
          </div>
        </div>

        <main className="flex items-center justify-center px-4 py-10 sm:px-6">
          <div className="w-full max-w-lg space-y-5">
            {demoState === 'loading' && (
              <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
                <LoaderCircle size={18} className="spin text-teal-700" />
                <span>Loading sample reports...</span>
              </div>
            )}

            {demoState === 'error' && (
              <div
                role="alert"
                className="rounded-xl border border-amber-200 bg-amber-50 p-6 text-sm text-amber-950"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-semibold">Sample reports could not be loaded</div>
                    <p className="mt-1 text-xs text-amber-900">
                      Check that the backend server is running and retry loading the sample cases.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={loadDemoSessions}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
                  >
                    <RefreshCw size={13} />
                    Retry
                  </button>
                </div>
              </div>
            )}

            {demoState === 'enabled' && personas.length > 0 && (
              <section className="rounded-xl border border-slate-200 bg-white p-6 sm:p-7">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h2 className="text-xl font-bold text-slate-900">Choose a sample report</h2>
                  <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                    Synthetic demo
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-slate-600">
                  Explore four fictional patient reports to see how CityLab explains results.
                </p>

                {error && (
                  <div role="alert" className="mt-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
                    {error}
                  </div>
                )}

                <div className="mt-5 grid gap-3 sm:grid-cols-2">
                  {personas.map((persona) => (
                    <button
                      key={persona.patient_id}
                      type="button"
                      disabled={busy}
                      onClick={() => authenticateWithToken(persona.token)}
                      className="flex flex-col justify-between rounded-lg border border-slate-200 bg-slate-50 p-4 text-left hover:border-teal-700 hover:bg-white"
                    >
                      <div>
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-sm font-bold text-slate-900">{persona.name}</span>
                          <span className="rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                            Synthetic demo
                          </span>
                        </div>
                        <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{persona.description}</p>
                      </div>
                      <div className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-teal-700">
                        <span>View report</span>
                        <ArrowRight size={14} />
                      </div>
                    </button>
                  ))}
                </div>
              </section>
            )}

            {demoState === 'disabled' ? (
              <section className="rounded-xl border border-slate-200 bg-white p-6 sm:p-7">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-teal-200 bg-teal-50 text-teal-700">
                  <LockKeyhole size={18} />
                </div>
                <h2 className="mt-4 text-xl font-bold text-slate-900">View your lab report</h2>
                <p className="mt-1 text-sm text-slate-600">
                  Use the code provided by your lab administrator.
                </p>

                <form onSubmit={handleLoginSubmit} className="mt-5 space-y-4">
                  <div>
                    <label htmlFor="access-key" className="block text-xs font-semibold text-slate-700">
                      Patient access code
                    </label>
                    <input
                      id="access-key"
                      type="password"
                      autoComplete="off"
                      required
                      value={draftKey}
                      onChange={(e) => setDraftKey(e.target.value)}
                      placeholder="Enter your private access code"
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
                    {busy ? <LoaderCircle size={16} className="spin" /> : <>View your report <ArrowRight size={16} /></>}
                  </button>
                </form>
              </section>
            ) : (
              <details className="rounded-xl border border-slate-200 bg-white px-5 py-4">
                <summary className="flex cursor-pointer list-none items-center justify-between text-xs font-semibold text-slate-700">
                  <span>Have a private access code?</span>
                  <ChevronDown size={15} className="text-slate-400" />
                </summary>
                <form onSubmit={handleLoginSubmit} className="mt-4 space-y-3 border-t border-slate-100 pt-4">
                  <div>
                    <label htmlFor="access-key" className="block text-xs font-semibold text-slate-700">
                      Patient access code
                    </label>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      Use the code provided by your lab administrator.
                    </p>
                    <input
                      id="access-key"
                      type="password"
                      autoComplete="off"
                      required
                      value={draftKey}
                      onChange={(e) => setDraftKey(e.target.value)}
                      placeholder="Enter your private access code"
                      className="mt-1.5 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={busy}
                    className="inline-flex items-center justify-center gap-2 rounded-md bg-slate-900 px-4 py-2 text-xs font-semibold text-white hover:bg-slate-800"
                  >
                    {busy ? <LoaderCircle size={14} className="spin" /> : <>View your report <ArrowRight size={14} /></>}
                  </button>
                </form>
              </details>
            )}
          </div>
        </main>
      </div>
    );
  }

  const resultsTable = (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 px-5 py-4">
        <div className="min-w-0">
          <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
            Detailed Laboratory Results
            <span className="rounded border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
              {results.length}
            </span>
          </h2>
          <p className="mt-0.5 text-xs text-slate-500">
            Click any row to inspect its plain-language explanation, calculation trace, and source document excerpt.
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
              className="w-36 bg-transparent text-slate-800 outline-none placeholder:text-slate-400 sm:w-40"
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
                {displayStatus(s)}
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
              <th className="px-4 py-3 text-right">Sources</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200 text-sm">
            {visibleResults.map((r) => {
              const isOpen = expandedRowId === r.measurement_id;
              return (
                <React.Fragment key={r.measurement_id}>
                  <tr
                    className={`cursor-pointer hover:bg-slate-50 ${isOpen ? 'bg-slate-50' : 'bg-white'}`}
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
                              Matched: {r.canonical_test_name}
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
                        aria-label={`View sources for ${r.test}`}
                        aria-expanded={isOpen}
                        className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 hover:bg-slate-100"
                      >
                        {isOpen ? (
                          <>
                            Hide <ChevronDown size={14} />
                          </>
                        ) : (
                          <>
                            View sources <ChevronRight size={14} />
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
          Classifications calculated deterministically from the loaded reference sheets
        </span>
      </div>
    </section>
  );

  const reportQuickTestPrompts = Array.from(
    new Set(results.slice(0, 3).map((r) => `Explain ${r.test}`))
  );
  const assistantSuggestions = [
    'Summarize this report',
    'Which results need attention?',
    'Explain a test',
    'Why are some results unclassified?',
    'What should I ask my doctor?',
    ...reportQuickTestPrompts,
  ];

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
          Workspace
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
              <label
                htmlFor="sample-patient-switcher"
                className="block px-1 text-[10px] font-semibold uppercase tracking-wider text-slate-500"
              >
                Switch sample patient
              </label>
              <select
                id="sample-patient-switcher"
                aria-label="Switch sample patient"
                value={session.patient.id}
                onChange={(e) => {
                  const chosen = personas.find((p) => p.patient_id === e.target.value);
                  if (chosen) authenticateWithToken(chosen.token);
                }}
                className="mt-1.5 w-full rounded-md border border-slate-300 bg-slate-50 px-2.5 py-2 text-xs font-medium text-slate-800"
              >
                {personas.map((p) => (
                  <option key={p.patient_id} value={p.patient_id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="rounded-md border border-slate-200 bg-slate-50 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
              <ShieldCheck size={15} className="text-teal-700" />
              Single-Patient Session
            </div>
            <p className="mt-1 text-[11px] leading-snug text-slate-600">
              Showing records only for <span className="font-semibold">{session.patient.name}</span>.
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

      <div className="flex min-w-0 flex-1 flex-col lg:pl-64">
        <header className="sticky top-0 z-10 flex h-16 items-center justify-between border-b border-slate-200 bg-white px-4 sm:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              aria-label="Open navigation"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="rounded-md border border-slate-200 p-2 text-slate-600 lg:hidden"
            >
              <Menu size={18} />
            </button>
            <div className="flex min-w-0 items-center gap-2 text-xs text-slate-500">
              <span>CityLab</span>
              <ChevronRight size={14} className="shrink-0" />
              <strong className="truncate font-semibold text-slate-900">{page}</strong>
            </div>
          </div>

          <div className="flex items-center gap-2.5">
            {isSyntheticContext && (
              <span className="inline-flex items-center rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-900">
                Synthetic demo
              </span>
            )}
            <div className="flex items-center gap-2">
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full border border-slate-200 bg-slate-100 text-xs font-semibold text-slate-700">
                {session.patient.name.slice(0, 1)}
              </span>
              <span className="hidden text-xs font-semibold text-slate-800 sm:inline">{session.patient.name}</span>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-7xl min-w-0 flex-1 space-y-6 px-4 py-6 sm:px-8">
          {isSyntheticContext && (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2.5 text-xs text-amber-950">
              <span className="rounded border border-amber-300 bg-white px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-900">
                Synthetic demo
              </span>
              <span>
                These sample patients and reference rules are fictional demonstration material, not real clinical records or medically validated guidelines.
              </span>
            </div>
          )}

          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="min-w-0">
              <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-teal-700">
                CityLab Diagnostics
              </div>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-slate-900">
                {page === 'Dashboard' ? 'Patient Laboratory Report' : page}
              </h1>
              <p className="mt-1 text-sm text-slate-600">
                {page === 'Report assistant'
                  ? 'Ask about a test, understand a result, or prepare questions for your doctor.'
                  : 'Inspect measurements, unit conversions, reference intervals, and source notes.'}
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
            <div className="flex min-w-0 items-center gap-3.5 md:col-span-4">
              <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full border border-slate-200 bg-slate-100 text-sm font-bold text-slate-700">
                <UserCheck size={18} />
              </div>
              <div className="min-w-0">
                <div className="truncate text-sm font-bold text-slate-900">{session.patient.name}</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {detail?.report.synthetic ? 'Synthetic sample record' : 'Uploaded report record'}
                </div>
              </div>
            </div>

            <div className="flex flex-wrap gap-6 border-t border-slate-200 pt-3 md:col-span-4 md:border-l md:border-t-0 md:pl-6 md:pt-0">
              <div>
                <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">Age at Report</div>
                <div className="mt-0.5 text-sm font-semibold text-slate-800">
                  {detail?.report.age_at_report ? (
                    `${detail.report.age_at_report} yrs`
                  ) : (
                    <span className="text-amber-700">Not provided</span>
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

            <div className="min-w-0 border-t border-slate-200 pt-3 md:col-span-4 md:border-t-0 md:pt-0">
              <label htmlFor="report-selector" className="block text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                Selected Report
              </label>
              <select
                id="report-selector"
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
              detail.report.demographics_overridden) && (
              <section className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <form
                  onSubmit={handleDemographicsUpdate}
                  className="flex flex-wrap items-end justify-between gap-4"
                >
                  <div className="max-w-xl">
                    <div className="text-xs font-bold text-amber-950">
                      {detail.report.age_at_report === null || detail.report.sex_at_report === 'unknown'
                        ? 'Missing Patient Information — No Defaults Assumed'
                        : 'Patient Information Supplied for Evaluation'}
                    </div>
                    <p className="mt-0.5 text-xs text-amber-900">
                      {detail.report.age_at_report === null || detail.report.sex_at_report === 'unknown'
                        ? 'Supply the patient age and biological sex from the requisition to evaluate age- or sex-dependent tests without guessing.'
                        : `Active evaluation uses your supplied age/sex (original report record: age ${
                            detail.report.original_age_at_report ?? 'missing'
                          }, sex ${detail.report.original_sex_at_report}).`}
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
                    {detail.report.demographics_overridden && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={handleDemographicsReset}
                        className="rounded-md border border-amber-300 bg-white px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
                      >
                        Reset to Original
                      </button>
                    )}
                  </div>
                </form>
              </section>
            )}

          {loading ? (
            <div role="status" className="flex flex-col items-center justify-center rounded-lg border border-slate-200 bg-white py-16">
              <LoaderCircle size={26} className="spin text-teal-700" />
              <div className="mt-3 text-sm font-semibold text-slate-800">Loading Laboratory Report</div>
              <p className="mt-1 text-xs text-slate-500">Checking measurements, ranges, and source citations.</p>
            </div>
          ) : !detail ? (
            <div className="flex flex-col items-center justify-center rounded-lg border border-slate-200 bg-white px-6 py-16 text-center">
              <FileText size={32} className="text-slate-400" />
              <h2 className="mt-3 text-base font-semibold text-slate-900">
                {reports.length ? 'Select a report above' : 'No laboratory reports on file'}
              </h2>
              <p className="mt-1 max-w-md text-xs text-slate-500">
                Upload a laboratory report in TXT, Markdown, CSV, JSON, or text PDF format containing a Test, Value, Unit table.
              </p>
            </div>
          ) : page === 'Patient Reports' ? (
            <section className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
                <div>
                  <h2 className="text-base font-semibold text-slate-900">Authorized Reports</h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Showing only records belonging to {session.patient.name}.
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
                    <div className="flex min-w-0 items-center gap-3.5">
                      <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-teal-200 bg-teal-50 text-teal-700">
                        <FileText size={17} />
                      </span>
                      <div className="min-w-0">
                        <div className="truncate text-sm font-semibold text-slate-900">
                          {formatDate(r.report_date)} — {r.source_file || r.id}
                        </div>
                        <div className="mt-0.5 text-xs text-slate-500">
                          {r.tests} measurements
                          {r.synthetic ? ' · Synthetic demo' : ' · Uploaded report'}
                        </div>
                      </div>
                    </div>
                    <ChevronRight size={17} className="shrink-0 text-slate-400" />
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
          ) : page === 'Report assistant' ? (
            <section className="mx-auto max-w-4xl overflow-hidden rounded-lg border border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-6 py-4">
                <div className="flex items-center gap-3">
                  <span className="grid h-9 w-9 shrink-0 place-items-center rounded-md border border-teal-200 bg-teal-50 text-teal-700">
                    <MessageSquare size={17} />
                  </span>
                  <div>
                    <h2 className="text-base font-semibold text-slate-900">Report assistant</h2>
                    <p className="text-xs text-slate-500">
                      Ask about a test, understand a result, or prepare questions for your doctor.
                    </p>
                  </div>
                </div>
                {detail.report.synthetic && (
                  <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[11px] font-medium text-slate-600">
                    Synthetic demo
                  </span>
                )}
              </div>

              {!session.ai_configured && (
                <div className="border-b border-slate-200 bg-slate-50 px-6 py-2 text-xs text-slate-600">
                  AI assistance is unavailable. You can still explore the verified report information.
                </div>
              )}

              <div className="h-[440px] space-y-4 overflow-y-auto bg-slate-50 p-5 sm:p-6" aria-live="polite">
                {chatHistory.length === 0 ? (
                  <div className="mx-auto max-w-xl py-6 text-center">
                    <MessageSquare size={28} className="mx-auto text-teal-700" />
                    <h3 className="mt-3 text-base font-semibold text-slate-900">
                      Ask about {session.patient.name}&apos;s report
                    </h3>
                    <p className="mt-1.5 text-xs leading-relaxed text-slate-600">
                      Ask about a specific test, filter by Normal/High/Low/Urgent results, check conversions, or get
                      questions for your doctor.
                    </p>
                    <div className="mt-5 flex flex-wrap justify-center gap-2">
                      {assistantSuggestions.map((prompt) => (
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
                  <>
                    <div className="flex flex-wrap gap-1.5 pb-1">
                      {assistantSuggestions.slice(0, 5).map((prompt) => (
                        <button
                          key={prompt}
                          type="button"
                          disabled={chatBusy}
                          onClick={() => handleAsk(undefined, prompt)}
                          className="rounded border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-medium text-slate-600 hover:border-teal-600 hover:text-teal-800"
                        >
                          {prompt}
                        </button>
                      ))}
                    </div>
                    {chatHistory.map((msg, idx) => (
                      <div
                        key={idx}
                        className={`max-w-[92%] rounded-lg border p-4 text-sm ${
                          msg.role === 'user'
                            ? 'ml-auto border-teal-200 bg-teal-50 text-slate-900'
                            : 'border-slate-200 bg-white text-slate-800'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-2 text-[11px] font-semibold text-slate-500">
                          <span>{msg.role === 'user' ? session.patient.name : 'Report assistant'}</span>
                          {msg.role === 'assistant' && (
                            <span className="rounded border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-medium text-slate-600">
                              {msg.ai_used ? 'AI-assisted explanation' : 'Report information'}
                            </span>
                          )}
                        </div>
                        <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed">{msg.text}</p>
                        {msg.report_urgent_notice && (
                          <div className="mt-3 rounded border border-red-200 bg-red-50 px-3 py-2 text-[11px] font-medium text-red-900">
                            {msg.report_urgent_notice}
                          </div>
                        )}
                        {msg.sources && msg.sources.length > 0 && (
                          <details className="mt-3 border-t border-slate-100 pt-2">
                            <summary className="cursor-pointer text-[11px] font-semibold text-teal-800">
                              View sources ({msg.sources.length})
                            </summary>
                            <div className="mt-2 space-y-1.5">
                              {msg.sources.map((src, sIdx) => (
                                <div key={sIdx} className="rounded border border-slate-200 bg-slate-50 p-2 text-[11px]">
                                  <div className="font-semibold text-slate-700">
                                    {src.test} · {src.file} ({src.location})
                                  </div>
                                  <div className="mt-0.5 break-words font-mono text-[10px] text-slate-600">
                                    {src.excerpt}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </details>
                        )}
                      </div>
                    ))}
                  </>
                )}
                {chatBusy && (
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <LoaderCircle size={14} className="spin text-teal-700" />
                    Checking report details...
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
                  placeholder="Ask about a test (e.g. Explain ALT), a follow-up (Is it high?), or Which results are normal?"
                  className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400"
                />
                <button
                  type="submit"
                  disabled={chatBusy || !question.trim()}
                  className="inline-flex shrink-0 items-center gap-2 rounded-md bg-teal-700 px-4 py-2 text-xs font-semibold text-white hover:bg-teal-800"
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
                  Server-Generated Report Summary PDF
                </div>
                <h2 className="text-2xl font-bold text-slate-900">Download Report Summary (PDF)</h2>
                <p className="text-sm text-slate-600">
                  Generates a formatted multi-page PDF directly from the current rules-engine analysis for{' '}
                  <strong>{session.patient.name}</strong>.
                  {detail.report.synthetic ? ' Includes synthetic demonstration disclosure.' : ''}
                </p>
                <ul className="grid gap-2 text-xs text-slate-700 sm:grid-cols-2">
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Patient demographics &amp; override distinction
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
                    <Check size={14} className="text-teal-700" /> Source file &amp; line references
                  </li>
                  <li className="flex items-center gap-2">
                    <Check size={14} className="text-teal-700" /> Missing data &amp; educational disclaimer
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
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-bold text-red-950">Urgent Clinical Attention Required</span>
                        {isSyntheticContext && (
                          <span className="rounded border border-red-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-red-800">
                            Synthetic demo rule
                          </span>
                        )}
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
                <div className="min-w-0 space-y-5 xl:col-span-8">
                  {resultsTable}

                  {/* Secondary Extraction & Security Notes */}
                  {(detail.metadata || detail.report.issues.length > 0) && (
                    <details className="rounded-lg border border-slate-200 bg-white px-5 py-3.5">
                      <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-2 text-xs font-semibold text-slate-700">
                        <span>Document processing notes ({detail.metadata?.source_file || detail.report.source_file || 'Uploaded'})</span>
                        <div className="flex items-center gap-2">
                          {detail.metadata?.prompt_injection_detected && (
                            <span className="rounded border border-amber-300 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-900">
                              Untrusted instructions ignored
                            </span>
                          )}
                          <ChevronDown size={15} className="text-slate-400" />
                        </div>
                      </summary>
                      <div className="mt-4 border-t border-slate-100 pt-4">
                        <div className="grid gap-3 text-xs text-slate-600 sm:grid-cols-3">
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
                              <li key={idx} className="break-words font-mono text-[11px]">
                                • {issue}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    </details>
                  )}

                  <div className="flex items-start gap-2.5 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600">
                    <ShieldCheck size={16} className="mt-0.5 shrink-0 text-teal-700" />
                    <p>{detail.analysis.disclaimer}</p>
                  </div>
                </div>

                <aside className="min-w-0 space-y-5 xl:col-span-4">
                  {/* Questions for your doctor */}
                  <section className="rounded-lg border border-slate-200 bg-white p-5">
                    <div className="flex items-center gap-2.5">
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-md border border-teal-200 bg-teal-50 text-teal-700">
                        <ClipboardList size={16} />
                      </span>
                      <div>
                        <h2 className="text-sm font-bold text-slate-900">Questions for Your Doctor</h2>
                        <p className="text-[11px] text-slate-500">Prepared from this report&apos;s findings</p>
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
                      Open Report assistant
                    </div>
                    <p className="mt-1.5 text-xs leading-relaxed text-teal-800">
                      Ask about a test, filter normal or out-of-range results, or get help preparing doctor questions.
                    </p>
                    <button
                      type="button"
                      onClick={() => navigateTo('Report assistant')}
                      className="mt-4 inline-flex w-full items-center justify-between rounded-md bg-teal-700 px-3.5 py-2 text-xs font-semibold text-white hover:bg-teal-800"
                    >
                      <span>Open Report assistant</span>
                      <ArrowRight size={15} />
                    </button>
                  </section>
                </aside>
              </div>
            </>
          )}

          <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-200 pt-5 text-[11px] text-slate-500">
            <span>CityLab Diagnostics · Medical Lab Report Explainer (JSON Storage Prototype)</span>
            <span>Tech Fusion &apos;26</span>
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
