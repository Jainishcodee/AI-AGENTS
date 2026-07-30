import { z } from "zod";

/**
 * A case is a hand-authored JSON file validated by this schema and gated by
 * `scripts/lint-case.ts`. The linter refuses cases that cannot be solved, which
 * is the failure mode hand-authored mysteries fall into most often.
 */

export const CLUE_TYPES = [
  "physical",
  "document",
  "statement",
  "forensic",
  "photo",
] as const;

export type ClueType = (typeof CLUE_TYPES)[number];

export const suspectSchema = z.object({
  id: z.string(),
  name: z.string(),
  occupation: z.string(),
  portrait: z.string().nullable().default(null),
  /** Public-facing description shown in the suspect dossier from the start. */
  summary: z.string(),
  /** What they claim they were doing. May be a lie — the case decides. */
  alibi: z.string(),
});

export const motiveSchema = z.object({
  id: z.string(),
  label: z.string(),
  description: z.string(),
});

export const clueSchema = z.object({
  id: z.string(),
  type: z.enum(CLUE_TYPES),
  title: z.string(),
  /** Rendered as CSS "paper" for documents, as a card otherwise. */
  body: z.string(),
  asset: z.string().nullable().default(null),
  isRedHerring: z.boolean().default(false),
  /** Suspect this clue points at, for the corkboard. */
  implicates: z.string().nullable().default(null),
  /** Clue ids that must already be discovered before this one can surface. */
  requires: z.array(z.string()).default([]),
  /** Sending this to the lab (4 time units) yields this clue id. */
  labResult: z.string().nullable().default(null),
});

export const questionSchema = z.object({
  id: z.string(),
  text: z.string(),
  answer: z.string(),
  /** Clue ids granted by asking. */
  grants: z.array(z.string()).default([]),
  /** Clue ids the team must hold before this question unlocks. */
  requires: z.array(z.string()).default([]),
});

export const npcSchema = z.object({
  id: z.string(),
  name: z.string(),
  role: z.string(),
  portrait: z.string().nullable().default(null),
  /** City location where this NPC can be found. */
  locationId: z.string(),
  questions: z.array(questionSchema).min(1),
});

export const caseLocationSchema = z.object({
  /** References an id in content/city.json. */
  cityLocationId: z.string(),
  /** Case-specific override of the city blurb. */
  description: z.string(),
  searchable: z.boolean().default(true),
  /** Clue ids findable here, subject to each clue's own `requires`. */
  clues: z.array(z.string()).default([]),
  searchCost: z.number().int().positive().default(2),
});

/**
 * Tutorial steps teach the five verbs and then get out of the way. Each step
 * declares a condition the engine can evaluate against game state, so progress
 * is driven by what the player actually did - never by a "next" button.
 */
export const tutorialConditionSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("atLocation"), locationId: z.string() }),
  z.object({ type: z.literal("searched"), locationId: z.string() }),
  z.object({ type: z.literal("hasClue"), clueId: z.string() }),
  z.object({
    type: z.literal("askedQuestion"),
    npcId: z.string(),
    questionId: z.string(),
  }),
  z.object({ type: z.literal("labTested"), clueId: z.string() }),
  z.object({ type: z.literal("caseClosed") }),
]);

export const tutorialStepSchema = z.object({
  id: z.string(),
  /** The verb being taught, e.g. "TRAVEL". Shown as a label. */
  verb: z.string(),
  title: z.string(),
  body: z.string(),
  done: tutorialConditionSchema,
});

export const solutionSchema = z.object({
  culpritId: z.string(),
  motiveId: z.string(),
  /** The three clues that actually prove it. */
  requiredEvidence: z.array(z.string()).min(1),
  epilogue: z.string(),
  /** Shown when the team accuses the wrong person. */
  failureEpilogue: z.string(),
});

export const caseSchema = z.object({
  id: z.string(),
  title: z.string(),
  cityId: z.string(),
  brief: z.string(),
  /**
   * Two clocks, doing two different jobs.
   *
   * `timeBudget` is the STORY clock, in hours. Actions cost it, it gates what
   * the team can still afford, and every case is balanced against it. It also
   * stamps each journal entry with an in-fiction date and time.
   *
   * `sessionMinutes` is the REAL clock: wall time at the table. It is the hard
   * limit a group actually feels. Whichever runs out first closes the case.
   */
  timeBudget: z.number().int().positive(),
  sessionMinutes: z.number().int().positive().default(90),
  /** In-fiction moment the case opens. Drives the journal's datelines. */
  startsAt: z.string().default("1984-05-25T08:00:00"),
  /** Where the team starts. Must be a city location id. */
  startLocationId: z.string(),
  suspects: z.array(suspectSchema).min(2),
  motives: z.array(motiveSchema).min(2),
  clues: z.array(clueSchema).min(1),
  npcs: z.array(npcSchema).default([]),
  locations: z.array(caseLocationSchema).min(1),
  /** Empty on ordinary cases; the demo case fills it in. */
  tutorial: z.array(tutorialStepSchema).default([]),
  solution: solutionSchema,
});

export type Suspect = z.infer<typeof suspectSchema>;
export type Motive = z.infer<typeof motiveSchema>;
export type Clue = z.infer<typeof clueSchema>;
export type Question = z.infer<typeof questionSchema>;
export type Npc = z.infer<typeof npcSchema>;
export type CaseLocation = z.infer<typeof caseLocationSchema>;
export type Solution = z.infer<typeof solutionSchema>;
export type TutorialCondition = z.infer<typeof tutorialConditionSchema>;
export type TutorialStep = z.infer<typeof tutorialStepSchema>;
export type CaseFile = z.infer<typeof caseSchema>;

/** Indexed view of a case, built once and reused by the reducer. */
export interface CaseIndex {
  file: CaseFile;
  clues: Map<string, Clue>;
  suspects: Map<string, Suspect>;
  motives: Map<string, Motive>;
  npcs: Map<string, Npc>;
  /** Keyed by city location id. */
  locations: Map<string, CaseLocation>;
  /** City location id -> NPCs standing there. */
  npcsByLocation: Map<string, Npc[]>;
  /** `${npcId}:${questionId}` -> question, for O(1) lookup. */
  questions: Map<string, Question>;
}

export function indexCase(file: CaseFile): CaseIndex {
  const npcsByLocation = new Map<string, Npc[]>();
  const questions = new Map<string, Question>();
  for (const npc of file.npcs) {
    const list = npcsByLocation.get(npc.locationId) ?? [];
    list.push(npc);
    npcsByLocation.set(npc.locationId, list);
    for (const q of npc.questions) questions.set(`${npc.id}:${q.id}`, q);
  }
  return {
    file,
    clues: new Map(file.clues.map((c) => [c.id, c])),
    suspects: new Map(file.suspects.map((s) => [s.id, s])),
    motives: new Map(file.motives.map((m) => [m.id, m])),
    npcs: new Map(file.npcs.map((n) => [n.id, n])),
    locations: new Map(file.locations.map((l) => [l.cityLocationId, l])),
    npcsByLocation,
    questions,
  };
}

export function parseCase(raw: unknown): CaseFile {
  return caseSchema.parse(raw);
}
