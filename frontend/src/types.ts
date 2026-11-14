export type Status = 'Normal' | 'Low' | 'High' | 'Urgent' | 'Cannot Be Classified';

export type KnowledgeProvenance = 'synthetic' | 'organizer_unreviewed' | 'organizer_reviewed';

export interface Evidence {
  file: string;
  location: string;
  excerpt: string;
}

export interface Patient {
  id: string;
  name: string;
  age: string | null;
  sex: string;
  profile_type?: 'demo' | 'personal';
  created_at?: string | null;
}

export interface AuthRegisterResponse {
  profile: Patient;
  access_code: string;
  session_token: string;
  expires_at: string;
}

export interface AuthLoginResponse {
  profile: Patient;
  session_token: string;
  expires_at: string;
}

export interface DemoPersona {
  patient_id: string;
  name: string;
  tag: string;
  description: string;
  token: string;
}

export interface Session {
  patient: Patient;
  knowledge_ready: boolean;
  knowledge_version: string;
  knowledge_provenance: KnowledgeProvenance;
  synthetic_demo: boolean;
  tests_count: number;
  ranges_count: number;
  urgent_rules_count: number;
  safety_rules_count: number;
  ai_configured: boolean;
  llm_provider: string;
  ocr_available?: boolean;
}

export interface ReportSummary {
  id: string;
  title?: string;
  report_date: string | null;
  uploaded_at?: string | null;
  review_status?: 'ready' | 'needs_review';
  name_mismatch_warning?: string | null;
  tests: number;
  synthetic: boolean;
  source_file?: string;
  has_source_file?: boolean;
  noise_lines_skipped?: number;
  prompt_injection_detected?: boolean;
  issues_count?: number;
}

export interface ReportMetadata {
  report_id: string;
  patient_id: string;
  source_file: string;
  source_hash: string;
  ingested_at: string;
  line_count: number;
  noise_lines_skipped: number;
  prompt_injection_detected: boolean;
  extraction_issues: string[];
}

export interface Result {
  measurement_id: string;
  test: string;
  canonical_test_id: string | null;
  canonical_test_name: string | null;
  value: string;
  unit: string;
  converted_value: string | null;
  converted_unit: string | null;
  status: Status;
  reference: string;
  explanation: string;
  reason: string;
  warnings: string[];
  audit: string[];
  evidence: Evidence[];
}

export interface MeasurementItem {
  id: string;
  test: string;
  value: string;
  unit: string;
  evidence?: Evidence;
  issue?: string | null;
  original_test?: string | null;
  original_value?: string | null;
  original_unit?: string | null;
  user_corrected?: boolean;
  corrected_at?: string | null;
  uncertain?: boolean;
}

export interface Detail {
  patient: Patient;
  metadata: ReportMetadata | null;
  analysis_revision?: string;
  report: {
    id: string;
    patient_id: string;
    title?: string;
    report_date: string | null;
    uploaded_at?: string | null;
    review_status?: 'ready' | 'needs_review';
    reviewed_at?: string | null;
    age_at_report: string | null;
    sex_at_report: string;
    original_age_at_report: string | null;
    original_sex_at_report: string;
    demographics_overridden: boolean;
    printed_patient_name?: string | null;
    printed_patient_id?: string | null;
    name_mismatch_warning?: string | null;
    name_mismatch_confirmed?: boolean;
    stored_filename?: string | null;
    source_media_type?: string | null;
    has_source_file?: boolean;
    measurements?: MeasurementItem[];
    issues: string[];
    source_file: string;
    synthetic: boolean;
  };
  analysis: {
    report_id: string;
    patient_id: string;
    knowledge_version: string;
    knowledge_provenance: KnowledgeProvenance;
    generated_at: string;
    results: Result[];
    counts: Record<Status, number>;
    doctor_questions: string[];
    ai_enhanced: boolean;
    disclaimer: string;
  };
}

export interface ChatSource {
  measurement_id: string;
  test: string;
  file: string;
  location: string;
  excerpt: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  text: string;
  ai_used?: boolean;
  sources?: ChatSource[];
  report_urgent_notice?: string | null;
}
