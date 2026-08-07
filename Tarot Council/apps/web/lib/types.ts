/**
 * Mirror of the API's wire contract (apps/api/app/schemas/).
 *
 * Hand-maintained rather than generated: the surface is small, and generating it
 * would add a build step to a boundary that changes rarely. If it drifts, the
 * artifact renderers degrade to the generic view rather than crashing — which is
 * also what happens for a Phase 5 module producing an artifact kind this build has
 * never heard of.
 */

export type ModuleId =
  | "analyst"
  | "tactician"
  | "strategist"
  | "psychologist"
  | "optimizer"
  | "ethicist"
  | (string & {});

export type Depth = "quick" | "standard" | "deep";
export type Role = "primary" | "advisory" | "critic";
export type Reversibility = "reversible" | "costly" | "one_way";
export type EvidenceStatus =
  | "given"
  | "inferred"
  | "assumed"
  | "speculative"
  | "unknown";

export interface Confidence {
  score: number;
  basis: string;
  falsifier: string;
}

export interface ArtifactRowRef {
  module: ModuleId;
  stage_id: string;
  kind: string;
  row_id: string | null;
}

export interface Artifact {
  kind: string;
  schema_version: number;
  module: ModuleId;
  stage_id: string;
  title: string;
  notes: string | null;
  data: Record<string, unknown>;
}

export interface Conclusion {
  stance: string;
  first_action: string;
  reasoning: string;
  key_claims: ArtifactRowRef[];
  confidence: Confidence;
  what_would_change_my_mind: string;
  cheapest_decisive_test: string | null;
  ethical_veto: boolean;
  veto_grounds: string | null;
  notes?: string | null;
}

export interface Option {
  id: string;
  label: string;
  description: string;
}

export interface DecisionContext {
  question: string;
  normalised: string;
  domains: string[];
  decision_type: string;
  options: Option[];
  actors: string[];
  constraints: string[];
  current_state: string;
  time_box: string | null;
  reversibility: Reversibility;
  stated_values: string[];
  missing_inputs: string[];
  is_decision: boolean;
}

export type CritiqueKind =
  | "unsupported"
  | "missing_factor"
  | "wrong_frame"
  | "overweighted"
  | "bias_fired"
  | "boundary_violation"
  | "strong_agreement";

export interface Critique {
  critic: ModuleId;
  target: ModuleId;
  target_ref: ArtifactRowRef | null;
  kind: CritiqueKind;
  statement: string;
  severity: number;
  bias_id: string | null;
}

export interface Revision {
  module: ModuleId;
  accepted: { from_module: ModuleId; what: string; how_it_changes_my_view: string }[];
  rejected: { from_module: ModuleId; what: string; why_rejected: string }[];
  stance: string;
  confidence: Confidence;
  delta: string;
}

export interface ModuleRun {
  module: ModuleId;
  program_version: number;
  role: Role;
  artifacts: Artifact[];
  conclusion: Conclusion | null;
  abstained: boolean;
  abstain_reason: string | null;
  abstained_at: string | null;
  usage: Usage;
}

export interface Usage {
  calls: number;
  input_tokens: number;
  output_tokens: number;
  repairs: number;
  by_model: Record<string, number>;
}

export interface Synthesis {
  debate_summary: string;
  expected_outcome: { statement: string; check_in_days: number; measurable_by: string };
  consensus: { point: string; modules: ModuleId[]; supported_by: ArtifactRowRef[] }[];
  disagreements: {
    issue: string;
    positions: { module: ModuleId; position: string }[];
    why_it_matters: string;
    what_would_resolve_it: string;
    resolved_by: string | null;
  }[];
  blind_spots_fired: {
    bias_id: string;
    module: ModuleId;
    evidence: string;
    corrected: boolean;
  }[];
  council_blind_spot: string;
  recommendation: {
    action: string;
    first_action: string;
    timeline: string;
    do_not: string[];
    conditions: string[];
  };
  confidence: Confidence;
  calibration_note: string;
  ethical_veto_response: string | null;
  minority_opinions: {
    module: ModuleId;
    position: string;
    when_it_would_be_right: string;
  }[];
  alternative_strategy: { action: string; trigger: string } | null;
  long_term_prediction: { horizon: string; prediction: string; confidence: number }[];
  information_to_gather: string[];
}

export interface Deliberation {
  id: string;
  created_at: string;
  question: string;
  preset: string;
  depth: string;
  context: DecisionContext;
  runs: ModuleRun[];
  critiques: Critique[];
  revisions: Revision[];
  synthesis: Synthesis | null;
  usage: Usage;
  program_versions: Record<ModuleId, number>;
}

/* ───────────────────────────────────────────────────────────────── trace ── */

export type TraceNodeKind =
  | "question"
  | "context"
  | "stage_artifact"
  | "conclusion"
  | "critique"
  | "revision"
  | "conflict"
  | "consensus"
  | "recommendation"
  | "abstention";

export type TraceEdgeKind =
  | "derives_from"
  | "critiques"
  | "revises"
  | "conflicts_with"
  | "supports"
  | "concludes";

export interface TraceNode {
  id: string;
  kind: TraceNodeKind;
  label: string;
  module: ModuleId | null;
  stage_id: string | null;
  artifact_kind: string | null;
  depth: number;
  status: "ok" | "repaired" | "failed";
  detail: string;
}

export interface TraceEdge {
  src: string;
  dst: string;
  kind: TraceEdgeKind;
  label: string;
}

export interface TraceGraph {
  nodes: TraceNode[];
  edges: TraceEdge[];
}

/* ──────────────────────────────────────────────────────────────── events ── */

export type EventType =
  | "stage_started"
  | "intake_complete"
  | "module_started"
  | "artifact_complete"
  | "artifact_invalid"
  | "module_complete"
  | "module_abstained"
  | "critique_complete"
  | "revision_complete"
  | "trace_updated"
  | "synthesis_complete"
  | "card_created"
  | "done"
  | "error";

export interface StreamEvent {
  type: EventType;
  payload: Record<string, any>;
}

/* ──────────────────────────────────────────────────────────────── modules ── */

export interface ModuleSpec {
  id: ModuleId;
  skin: { name: string; title: string; accent: string };
  summary: string;
  mental_model: string;
  stages: {
    id: string;
    name: string;
    produces: string;
    group: string;
    terminal: boolean;
    must_not: string[];
  }[];
  biases: {
    id: string;
    description: string;
    hidden_from_self: boolean;
    detectable_by: ModuleId[];
  }[];
  critics: ModuleId[];
  success_metrics: { id: string; question: string; horizon_days: number }[];
  risk_tolerance: number;
  time_horizon: string;
  veto_enabled: boolean;
  calls_per_depth: Record<Depth, number>;
}

export interface PresetSpec {
  id: string;
  name: string;
  description: string;
  primary: ModuleId[];
  advisory: ModuleId[];
  critic: ModuleId[];
}
