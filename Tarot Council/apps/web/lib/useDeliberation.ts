"use client";

/**
 * A reducer over the typed event stream.
 *
 * No state library. The backend already emits a state machine — `module_started`,
 * `artifact_complete`, `module_abstained`, `synthesis_complete` — so a reducer over
 * those events *is* the client state, and adding a store would only add a second
 * description of the same thing.
 */

import { useCallback, useReducer, useRef } from "react";
import { sendJSON, streamEvents } from "./stream";
import type {
  Artifact,
  Conclusion,
  Critique,
  DecisionContext,
  Deliberation,
  Depth,
  ModuleId,
  Revision,
  Role,
  StreamEvent,
  Synthesis,
  TraceGraph,
  Usage,
} from "./types";

export interface LiveModule {
  module: ModuleId;
  role: Role;
  artifacts: Artifact[];
  conclusion: Conclusion | null;
  running: boolean;
  abstained: boolean;
  abstainReason: string | null;
  /** Validation complaints, kept even after a successful repair. The fact that a
   *  stage had to be repaired is part of an honest reasoning record. */
  problems: { stageId: string; problems: string[]; repaired: boolean }[];
  critiquesMade: number;
  revision: Revision | null;
}

export type Phase =
  | "idle"
  | "intake"
  | "reason"
  | "critique"
  | "revise"
  | "synthesis"
  | "done"
  | "failed";

export interface State {
  phase: Phase;
  phaseLabel: string;
  runId: string | null;
  /** Facts supplied while the council was still running, in the order applied. */
  injected: string[];
  question: string;
  context: DecisionContext | null;
  /** Keyed by module id. A plain string index, not `Record<ModuleId, …>`: ModuleId
   *  is an open union, so a total Record would demand every built-in key up front
   *  and would still not admit a Phase 5 module. */
  modules: Record<string, LiveModule>;
  order: ModuleId[];
  critiques: Critique[];
  revisions: Revision[];
  synthesis: Synthesis | null;
  trace: TraceGraph | null;
  deliberation: Deliberation | null;
  cardId: string | null;
  usage: Usage | null;
  warnings: string[];
  error: string | null;
}

const EMPTY: State = {
  phase: "idle",
  phaseLabel: "",
  runId: null,
  injected: [],
  question: "",
  context: null,
  modules: {},
  order: [],
  critiques: [],
  revisions: [],
  synthesis: null,
  trace: null,
  deliberation: null,
  cardId: null,
  usage: null,
  warnings: [],
  error: null,
};

type Action =
  | { kind: "start"; question: string }
  | { kind: "event"; event: StreamEvent }
  | { kind: "reset" };

const PHASE_OF: Record<string, Phase> = {
  intake: "intake",
  reason: "reason",
  critique: "critique",
  revise: "revise",
  synthesis: "synthesis",
};

function blank(module: ModuleId, role: Role = "primary"): LiveModule {
  return {
    module,
    role,
    artifacts: [],
    conclusion: null,
    running: true,
    abstained: false,
    abstainReason: null,
    problems: [],
    critiquesMade: 0,
    revision: null,
  };
}

function withModule(
  state: State,
  module: ModuleId,
  update: (current: LiveModule) => LiveModule,
): State {
  const current = state.modules[module] ?? blank(module);
  return {
    ...state,
    order: state.order.includes(module) ? state.order : [...state.order, module],
    modules: { ...state.modules, [module]: update(current) },
  };
}

function reduce(state: State, action: Action): State {
  if (action.kind === "reset") return EMPTY;
  if (action.kind === "start") {
    return { ...EMPTY, phase: "intake", question: action.question, phaseLabel: "Reading the question" };
  }

  const { type, payload } = action.event;

  switch (type) {
    case "run_started":
      // A run is addressable from its first event, so the interjection control can
      // appear immediately rather than after the first module finishes.
      return { ...state, runId: payload.run_id as string };

    case "injection_applied":
      return { ...state, injected: [...state.injected, ...(payload.facts as string[])] };

    case "stage_started":
      return {
        ...state,
        phase: PHASE_OF[payload.phase as string] ?? state.phase,
        phaseLabel: payload.label ?? payload.phase ?? "",
      };

    case "intake_complete":
      return { ...state, context: payload.context as DecisionContext };

    case "module_started":
      return withModule(state, payload.module, (current) => ({
        ...current,
        role: (payload.role as Role) ?? current.role,
        running: true,
      }));

    case "artifact_complete": {
      const artifact = payload.artifact as Artifact;
      return withModule(state, payload.module, (current) => ({
        ...current,
        // Replace on repeat so a re-run of a stage does not duplicate it.
        artifacts: [
          ...current.artifacts.filter((a) => a.stage_id !== artifact.stage_id),
          artifact,
        ],
      }));
    }

    case "artifact_invalid":
      return withModule(state, payload.module, (current) => ({
        ...current,
        problems: [
          ...current.problems,
          {
            stageId: payload.stage_id,
            problems: (payload.problems ?? []) as string[],
            repaired: Boolean(payload.repairing),
          },
        ],
      }));

    case "module_complete":
      return withModule(state, payload.module, (current) => ({
        ...current,
        running: false,
        conclusion: (payload.conclusion as Conclusion | null) ?? current.conclusion,
      }));

    case "module_abstained":
      return withModule(state, payload.module, (current) => ({
        ...current,
        running: false,
        abstained: true,
        abstainReason: payload.reason ?? null,
      }));

    case "critique_complete": {
      const incoming = (payload.critiques ?? []) as Critique[];
      const next = withModule(state, payload.module, (current) => ({
        ...current,
        critiquesMade: current.critiquesMade + incoming.length,
      }));
      return { ...next, critiques: [...next.critiques, ...incoming] };
    }

    case "revision_complete": {
      const revision = payload.revision as Revision;
      const next = withModule(state, revision.module, (current) => ({
        ...current,
        revision,
        // Synthesis weighs the revised confidence, so the UI shows that number too.
        conclusion: current.conclusion
          ? { ...current.conclusion, confidence: revision.confidence, stance: revision.stance }
          : current.conclusion,
      }));
      return { ...next, revisions: [...next.revisions, revision] };
    }

    case "trace_updated":
      return { ...state, trace: payload as unknown as TraceGraph };

    case "synthesis_complete":
      return { ...state, synthesis: payload.synthesis as Synthesis };

    case "card_created":
      return { ...state, cardId: payload.card_id ?? null };

    case "done":
      return {
        ...state,
        phase: "done",
        phaseLabel: "",
        deliberation: payload.deliberation as Deliberation,
        trace: (payload.trace as TraceGraph) ?? state.trace,
        usage: (payload.usage as Usage) ?? state.usage,
      };

    case "error":
      // Recoverable errors are warnings — a degraded intake or one failed critique
      // must not present as a dead deliberation.
      return payload.recoverable
        ? { ...state, warnings: [...state.warnings, String(payload.message)] }
        : { ...state, phase: "failed", error: String(payload.message) };

    default:
      return state;
  }
}

export function useDeliberation() {
  const [state, dispatch] = useReducer(reduce, EMPTY);
  const abort = useRef<AbortController | null>(null);
  const latest = useRef<string | null>(null);

  const run = useCallback(
    async (input: { question: string; preset: string; depth: Depth; notes?: string }) => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      dispatch({ kind: "start", question: input.question });

      try {
        for await (const event of streamEvents(
          {
            question: input.question,
            preset: input.preset,
            depth: input.depth,
            context_notes: input.notes ?? "",
          },
          controller.signal,
        )) {
          dispatch({ kind: "event", event });
        }
      } catch (error) {
        if ((error as Error).name !== "AbortError") {
          dispatch({
            kind: "event",
            event: { type: "error", payload: { message: String(error), recoverable: false } },
          });
        }
      }
    },
    [],
  );

  const inject = useCallback(
    async (facts: string[]) => {
      const runId = latest.current;
      if (!runId || !facts.length) return;
      await sendJSON(`council/live/${runId}/inject`, { facts });
    },
    [],
  );

  const cancel = useCallback(() => abort.current?.abort(), []);
  const reset = useCallback(() => {
    abort.current?.abort();
    dispatch({ kind: "reset" });
  }, []);

  // Kept in a ref as well as in state: `inject` must read the current run id without
  // being re-created on every event, or the caller's handler goes stale mid-run.
  latest.current = state.runId;

  return { state, run, cancel, reset, inject };
}

export const isBusy = (phase: Phase) =>
  phase !== "idle" && phase !== "done" && phase !== "failed";
