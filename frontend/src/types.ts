export type Status = 'Normal' | 'Low' | 'High' | 'Urgent' | 'Cannot Be Classified';

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
  tests_count: number;
  ranges_count: number;
  urgent_rules_count: number;
  safety_rules_count: number;
  ai_configured: boolean;
  llm_provider: string;
}

export interface ReportSummary {
  id: string;
  report_date: string | null;
  tests: number;
  synthetic: boolean;
  source_file?: string;
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

export interface Detail {
  patient: Patient;
  metadata: ReportMetadata | null;
  report: {
    id: string;
    patient_id: string;
    report_date: string | null;
    age_at_report: string | null;
    sex_at_report: string;
    issues: string[];
    source_file: string;
    synthetic: boolean;
  };
  analysis: {
    report_id: string;
    patient_id: string;
    knowledge_version: string;
    generated_at: string;
    results: Result[];
    counts: Record<Status, number>;
    doctor_questions: string[];
    ai_enhanced: boolean;
    disclaimer: string;
  };
}
