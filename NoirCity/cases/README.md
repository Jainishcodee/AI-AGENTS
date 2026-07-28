# Cases

## The rule that governs all of them

**Every case has a rational solution.** Backlund has cults, seances, sealed
artifacts and a Church that keeps files on things it will not discuss — and none
of it ever did the murder. The medium is always a fraud. The occult is the
*atmosphere* and, more usefully, the *misdirection*: the fraud is how you catch
the killer, because a person running a trick has to control a room, and
controlling a room leaves marks.

This is not a limitation, it is what makes the game playable. If a ritual could
have done it, the player cannot reason, and a mystery you cannot reason about is
a coin toss with extra reading.

## On the source material

These are original cases. They borrow *techniques and archetypes* from the
detective tradition — never plots, never characters, never names.

The distinction matters practically, not just legally: a case whose solution a
player already knows from television is not a case. It tests who watched the
episode. What travels is the **method of thinking**, and that is what each case
below is built to teach.

| Borrowed from | What actually travels |
|---|---|
| Hardboiled noir (Chandler, Hammett) | The client is lying to you too. Institutions are the antagonist. |
| Closed-circle (Christie) | A fixed cast, all present, all with reason. The alibi *structure* is the puzzle. |
| Observational deduction (*The Mentalist*) | The killer is caught by behaviour, not forensics. A cold reader's own tricks used against them. |
| Confession-driven (*Lucifer*) | Interrogation as the primary verb. Everybody tells you what they want if you ask correctly. |
| Trace evidence (Holmes) | Physical minutiae — paint, mud, ink, paper stock — that only mean something in combination. |
| Procedural / bent-police | The official record is evidence *about the police*, not about the crime. |

## Shipped

### `case-00-the-quiet-room` — the demo
**Small, hard, and teaches the five verbs.** 3 suspects, 12 clues, 5 locations,
32 hours. A widow dies at a seance in Cherwood; the physician at the table signs
her off inside the hour.

The tutorial covers TRAVEL → SEARCH → INTERVIEW → LAB → ACCUSE and then stops.
No hints about *thinking* — the player makes the final deduction unaided.

The misdirection is the whole point: Madame Roux is a proven fraud who will
cheerfully confess to every part of the fraud, and the eleven minutes of darkness
she needs for her trick look exactly like the murder window. They are not. The
digitalis was in the cup before the lamp went out.

*Blend: observational deduction + closed circle.*

### `case-01-harbor-lights` — the first real case
5 suspects, 19 clues, 6 NPCs, 14 locations, 48 hours. A dockworker at the bottom
of a dry dock that has been empty three weeks. Requires crossing the Tussock
repeatedly, so the river surcharge bites.

*Blend: hardboiled noir + trace evidence.*

## Planned

Each keeps the rational rule. Listed with the technique it is built to teach.

| # | Working title | Setting | Technique | Occult dressing |
|---|---|---|---|---|
| 02 | *The Bell Does Not Lie* | Empress Borough, civic quarter | **Closed circle.** Nine people at a dinner, one dead, the doors watched all evening. The alibi lattice is the puzzle — every statement constrains another. | The Bell of Order tolled off-schedule that night. There is a mundane reason. |
| 03 | *A Reading for Mr. Pell* | Vermilion, the strip | **Observational deduction.** A cold reader is murdered by someone they read correctly. Solved by reconstructing what the victim *deduced* about their killer. | A Church of Steam diviner offers a prophecy that is, read properly, a description of a bank ledger. |
| 04 | *What You Actually Want* | Cherwood + Coldbath | **Confession-driven.** Almost no physical evidence. Nearly every clue comes from interrogation; questions unlock other questions rather than unlocking searches. | An asylum ward where four patients describe the same dream. One of them was awake. |
| 05 | *The Sealed Room at St. Maar* | Coldbath | **Trace evidence + bent police.** A locked cell, a dead prisoner, a duty book that has been rewritten. The official record is the crime scene. | A "sealed artifact" in the prison property store that everyone is afraid of and nobody has opened. |

### Authoring notes

- **Red herrings must implicate specific suspects.** The linter warns on any
  suspect no clue points at. A suspect nothing accuses is scenery.
- **Gate at least one required clue behind another**, so the player has to
  return somewhere. That return trip is what makes the time budget bite.
- **Budget for roughly twice the direct route.** The linter reports the direct
  cost; aim for a case where wandering is affordable but not free.
- **Run the linter before committing:** `npm run lint:case cases/<dir>`. It
  refuses unsolvable chains, circular requirements, herrings used as proof,
  and tutorial steps that can soft-lock.
- **Add a playthrough test** in `lib/engine/playthrough.test.ts`. The linter
  proves a case is theoretically solvable; the playthrough proves a real
  sequence of actions actually solves it inside the budget.
