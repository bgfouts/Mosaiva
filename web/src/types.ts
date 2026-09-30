export type Evidence = {
  id: number;
  text: string;
  direction: "supports" | "contradicts";
  strength: "weak" | "moderate" | "strong";
  hypothesis_id: number | null;
  created_at: string | null;
};

export type Hypothesis = {
  id: number;
  title: string;
  statement: string;
  why_it_fits: string;
  confidence: string;
  likely_role: string;
  position: number;
  domains: string[];
  status: "active" | "parked" | "refuted" | "supported";
  probability: number;
  why_moved: string;
  evidence: Evidence[];
};

export type Intervention = {
  id: number;
  name: string;
  category: "medication" | "lifestyle" | "diet" | "supplement" | "therapy";
  dose: string;
  schedule: string;
  clinician_prescribed: boolean;
  status: "active" | "paused" | "stopped" | "ask_clinician";
  start_date: string | null;
  stop_date: string | null;
  benefit: number | null;
  side_effect_burden: number | null;
  net_value: number | null;
  side_effect_notes: string;
  clinician_task: string;
  hypothesis_ids: number[];
  hypotheses: { id: number; title: string }[];
};

export type ResearchItem = {
  id: number;
  title: string;
  journal: string;
  year: number | null;
  pdf_url: string;
  excerpt: string;
  query: string;
  relevance_note: string;
  hypothesis_ids: number[];
  intervention_ids: number[];
};

export type Capture = {
  id: number;
  tool_name: string;
  payload: Record<string, unknown>;
  status: "pending" | "committed" | "discarded";
};

export type CoachSession = {
  id: number;
  status: string;
  transcript: { role: "patient" | "coach"; text: string }[];
  urgent: boolean;
  captures: Capture[];
};

export type Review = {
  id: number;
  week_start: string;
  status: "proposed" | "accepted" | "dismissed";
  hypothesis_updates: {
    hypothesis_id: number;
    title?: string;
    previous_probability?: number;
    probability: number;
    rationale: string;
  }[];
  recommendation: {
    action: "add" | "remove" | "hold";
    intervention_id?: number | null;
    name?: string;
    category?: string | null;
    rationale?: string;
    what_to_watch?: string;
    safety_note?: string;
    dose?: string;
  };
};

export type Settings = {
  timezone: string;
  display_name: string;
};

export const DOMAINS = [
  "sleep",
  "pain",
  "GI",
  "autonomic",
  "immune",
  "endocrine",
  "metabolic",
  "mood",
  "cognition",
  "musculoskeletal",
  "skin",
  "heart/lungs",
];

export const TIMEZONES = [
  "UTC",
  "America/Los_Angeles",
  "America/Denver",
  "America/Chicago",
  "America/New_York",
  "Europe/London",
  "Europe/Paris",
  "Asia/Tokyo",
  "Australia/Sydney",
];
