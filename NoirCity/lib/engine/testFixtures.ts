import { indexCase, parseCase, type CaseIndex } from "./caseSchema";
import { indexCity, type City, type CityIndex } from "./citySchema";

/**
 * A four-location toy city and a small case, built so the engine can be tested
 * without loading half a megabyte of Marrowgate. Two boroughs per bank, so the
 * river surcharge is exercised.
 */

const TOY_CITY: City = {
  id: "toy",
  name: "Toy City",
  size: [1000, 1000],
  river: {
    name: "The Test",
    points: [
      [0, 500],
      [1000, 500],
    ],
    polygon: [
      [0, 540],
      [1000, 540],
      [1000, 460],
      [0, 460],
    ],
    widthAtSource: 80,
    widthAtMouth: 80,
  },
  bridges: [
    { id: "br", name: "Test Bridge", kind: "bridge", points: [[500, 600], [500, 400]] },
  ],
  railways: [],
  boroughs: [
    { id: "n1", name: "North One", bank: "north", polygon: [], neighbors: ["n2"], pattern: "grid", blurb: "", character: "" },
    { id: "n2", name: "North Two", bank: "north", polygon: [], neighbors: ["n1"], pattern: "grid", blurb: "", character: "" },
    { id: "s1", name: "South One", bank: "south", polygon: [], neighbors: [], pattern: "grid", blurb: "", character: "" },
  ],
  streets: [],
  blocks: [],
  locations: [
    { id: "office", name: "The Office", type: "office", boroughId: "n1", streetId: "st", address: "1 Test St", x: 100, y: 800, blurb: "", isLandmark: true },
    { id: "bar", name: "The Bar", type: "bar", boroughId: "n1", streetId: "st", address: "2 Test St", x: 200, y: 800, blurb: "A bar.", isLandmark: false },
    { id: "shop", name: "The Shop", type: "pawnshop", boroughId: "n2", streetId: "st", address: "3 Test St", x: 800, y: 800, blurb: "", isLandmark: false },
    { id: "dock", name: "The Dock", type: "pier", boroughId: "s1", streetId: "st", address: "4 Test St", x: 800, y: 200, blurb: "", isLandmark: false },
  ],
};

const TOY_CASE = {
  id: "toy-case",
  title: "The Toy Case",
  cityId: "toy",
  brief: "Someone did something.",
  timeBudget: 20,
  startLocationId: "office",
  suspects: [
    { id: "s_guilty", name: "Guilty Party", occupation: "Fence", summary: "", alibi: "" },
    { id: "s_innocent", name: "Innocent Party", occupation: "Clerk", summary: "", alibi: "" },
  ],
  motives: [
    { id: "m_money", label: "Money", description: "" },
    { id: "m_spite", label: "Spite", description: "" },
  ],
  clues: [
    { id: "c_open", type: "physical", title: "Open Clue", body: "Found freely." },
    // Gated behind c_open, so it cannot be picked up on a first search.
    { id: "c_gated", type: "document", title: "Gated Clue", body: "Needs the first.", requires: ["c_open"] },
    { id: "c_lab", type: "physical", title: "Bloodied Rag", body: "Send to the lab.", labResult: "c_labresult" },
    { id: "c_labresult", type: "forensic", title: "Lab Report", body: "It matches." },
    { id: "c_talk", type: "statement", title: "What Sal Said", body: "He talked." },
    { id: "c_herring", type: "physical", title: "Red Herring", body: "Means nothing.", isRedHerring: true },
  ],
  npcs: [
    {
      id: "n_sal",
      name: "Sal",
      role: "Barman",
      locationId: "bar",
      questions: [
        { id: "q_open", text: "What happened?", answer: "Nothing.", grants: ["c_talk"] },
        { id: "q_locked", text: "Explain the ledger.", answer: "Fine, I took it.", requires: ["c_gated"], grants: ["c_herring"] },
      ],
    },
  ],
  locations: [
    { cityLocationId: "bar", description: "The bar.", clues: ["c_open", "c_gated"], searchCost: 2 },
    { cityLocationId: "shop", description: "The shop.", clues: ["c_lab", "c_herring"], searchCost: 2 },
  ],
  solution: {
    culpritId: "s_guilty",
    motiveId: "m_money",
    requiredEvidence: ["c_open", "c_gated", "c_labresult"],
    // Deliberately disjoint vocabularies, so a test argument can make one point
    // without accidentally making another and the offline grader's arithmetic
    // stays readable in the assertions.
    keyPoints: [
      {
        id: "kp_money",
        claim: "They were being paid to keep quiet, and the payments stopped.",
        keywords: ["payment", "paid", "money", "quiet"],
      },
      {
        id: "kp_time",
        claim: "They were at the bar an hour before anybody says they arrived.",
        keywords: ["hour", "early", "bar", "before"],
      },
    ],
    epilogue: "You got them.",
    failureEpilogue: "They walked.",
  },
};

export function toyCity(): CityIndex {
  return indexCity(TOY_CITY);
}

export function toyCase(): CaseIndex {
  return indexCase(parseCase(TOY_CASE));
}
