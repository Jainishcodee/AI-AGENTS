"use client";

/**
 * Artifact renderer registry — the client mirror of `ARTIFACT_MODELS`.
 *
 * Dispatch is by `kind`, with a generic fallback rather than a crash. That matters
 * beyond robustness: a Phase 5 user-authored module will produce artifact kinds this
 * build has never heard of, and the right behaviour is to show the data plainly
 * rather than to refuse.
 */

import type { ReactNode } from "react";
import type { Artifact, EvidenceStatus } from "@/lib/types";
import {
  Bullets,
  Cell,
  Chip,
  Empty,
  Label,
  Meter,
  Pips,
  Row,
  RowId,
  StatusDot,
  Table,
} from "@/components/ui";
import { ProbabilityTree } from "./ProbabilityTree";
import { StakeholderGraph } from "./StakeholderGraph";
import { ProfileSet } from "./ProfileSet";

type Data = Record<string, any>;
interface Ctx {
  accent: string;
}
type Renderer = (data: Data, ctx: Ctx) => ReactNode;

/* ─────────────────────────────────────────────────────────────── helpers ── */

function Fields({ items }: { items: [string, ReactNode][] }) {
  const present = items.filter(([, value]) => value !== null && value !== undefined && value !== "");
  if (!present.length) return <Empty>Nothing recorded.</Empty>;
  return (
    <dl className="space-y-2">
      {present.map(([label, value]) => (
        <div key={label} className="flex flex-col gap-0.5 sm:flex-row sm:gap-3">
          <dt className="label shrink-0 pt-[3px] sm:w-[136px]">{label}</dt>
          <dd className="flex-1 text-[13px] leading-relaxed">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function Hero({ children, accent }: { children: ReactNode; accent: string }) {
  return (
    <div
      className="rounded border-l-2 bg-[var(--color-raised)] px-3 py-2 text-[13.5px] leading-relaxed"
      style={{ borderColor: accent }}
    >
      {children}
    </div>
  );
}

const REVERSIBILITY: Record<string, { label: string; colour: string }> = {
  reversible: { label: "reversible", colour: "var(--color-given)" },
  costly: { label: "costly to undo", colour: "var(--color-assumed)" },
  one_way: { label: "one-way door", colour: "var(--color-speculative)" },
};

function Reversibility({ value }: { value: string }) {
  const spec = REVERSIBILITY[value] ?? { label: value, colour: undefined as unknown as string };
  return <Chip colour={spec.colour}>{spec.label}</Chip>;
}

const COST_COLOUR: Record<string, string> = {
  free: "var(--color-given)",
  cheap: "var(--color-given)",
  expensive: "var(--color-assumed)",
  impossible: "var(--color-speculative)",
};

const SOURCE_QUALITY_COLOUR: Record<string, string> = {
  measured: "var(--color-given)",
  reported: "var(--color-inferred)",
  estimated: "var(--color-assumed)",
  guessed: "var(--color-speculative)",
};

const VERDICT_COLOUR: Record<string, string> = {
  keep: "var(--color-given)",
  cut: "var(--color-speculative)",
  automate: "var(--color-inferred)",
  delegate: "var(--color-inferred)",
  defer: "var(--color-assumed)",
};

const VALUE_SOURCE_COLOUR: Record<string, string> = {
  stated_by_user: "var(--color-given)",
  inferred_from_user: "var(--color-inferred)",
  conventional: "var(--color-assumed)",
};

const TAG_COLOUR: Record<string, string> = {
  obvious: "var(--color-unknown)",
  conventional: "var(--color-unknown)",
  inverse: "var(--color-inferred)",
  free: "var(--color-given)",
  reckless: "var(--color-speculative)",
  reframes: "var(--color-assumed)",
  hybrid: "var(--color-inferred)",
};

function Quote({ children }: { children: ReactNode }) {
  return (
    <span className="serif text-[13.5px] italic text-[var(--color-text)]">“{children}”</span>
  );
}

/* ───────────────────────────────────────────────────────────── renderers ── */

const RENDERERS: Record<string, Renderer> = {
  /* ── analyst ─────────────────────────────────────────────────────────── */

  DecisionFrame: (d, { accent }) => (
    <div className="space-y-3">
      <Hero accent={accent}>{d.the_actual_choice}</Hero>
      <Table head={["", "option"]}>
        {(d.options ?? []).map((option: Data) => (
          <Row key={option.id} id={option.id}>
            <Cell width="52px">
              <RowId id={option.id} />
            </Cell>
            <Cell>
              <span className="font-medium">{option.label}</span>
              {option.description && (
                <div className="text-[12px] text-[var(--color-muted)]">{option.description}</div>
              )}
            </Cell>
          </Row>
        ))}
      </Table>
      <Fields
        items={[
          ["reversibility", <Reversibility value={d.reversibility} />],
          ["decide by", d.time_box],
          [
            "success looks like",
            (d.success_criteria ?? []).length > 0 ? <Bullets items={d.success_criteria} /> : null,
          ],
        ]}
      />
    </div>
  ),

  EvidenceLedger: (d, { accent }) => (
    <Table
      head={["", "claim", "source", { label: "conf.", align: "right" }]}
    >
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.id} id={row.id}>
          <Cell width="58px">
            <span className="flex items-center gap-1.5">
              <StatusDot status={row.status as EvidenceStatus} />
              <RowId id={row.id} />
            </span>
          </Cell>
          <Cell>
            <span className={row.load_bearing ? "text-[var(--color-text)]" : undefined}>
              {row.statement}
            </span>
            {row.load_bearing && (
              <span className="ml-1.5 align-middle">
                <Chip colour={accent} title="The decision changes if this is false">
                  load-bearing
                </Chip>
              </span>
            )}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">{row.source || "—"}</Cell>
          <Cell align="right">
            <Meter value={row.confidence ?? 0} colour="var(--color-faint)" width={34} />
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  EvidenceGaps: (d) => (
    <Table head={["", "unknown", "why it matters", "cost"]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.id} id={row.id}>
          <Cell width="48px">
            <RowId id={row.id} />
          </Cell>
          <Cell>
            {row.question}
            {row.would_change_decision && (
              <span className="ml-1.5 align-middle">
                <Chip colour="var(--color-assumed)">would change the answer</Chip>
              </span>
            )}
            {row.how_to_resolve && (
              <div className="text-[12px] text-[var(--color-faint)]">→ {row.how_to_resolve}</div>
            )}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">{row.why_it_matters}</Cell>
          <Cell width="84px">
            <Chip colour={COST_COLOUR[row.cost_to_resolve]}>{row.cost_to_resolve}</Chip>
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  BaseRateTable: (d) => (
    <Table head={["reference class", "rate", "quality", { label: "applies", align: "right" }]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.id} id={row.id}>
          <Cell>{row.reference_class}</Cell>
          <Cell className="mono text-[12px]">{row.observed_rate}</Cell>
          <Cell width="92px">
            <Chip colour={SOURCE_QUALITY_COLOUR[row.source_quality]}>{row.source_quality}</Chip>
          </Cell>
          <Cell align="right" width="86px">
            <Meter value={row.applicability ?? 0} colour="var(--color-faint)" width={34} />
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  ProbabilityTree: (d, { accent }) => <ProbabilityTree data={d} accent={accent} />,

  FailureModeTable: (d) => (
    <Table head={["", "it failed because", "seen coming by", { label: "sev.", align: "right" }]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.id} id={row.id}>
          <Cell width="48px">
            <RowId id={row.id} />
          </Cell>
          <Cell>
            {row.scenario}
            {row.trigger && (
              <div className="text-[12px] text-[var(--color-faint)]">trigger: {row.trigger}</div>
            )}
            {row.mitigation && (
              <div className="text-[12px] text-[var(--color-muted)]">→ {row.mitigation}</div>
            )}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">{row.early_warning_signal}</Cell>
          <Cell align="right" width="70px">
            <span className="flex items-center justify-end gap-2">
              <Pips value={row.severity ?? 0} colour="var(--color-speculative)" />
            </span>
            <div className="mono mt-0.5 text-[10px] text-[var(--color-faint)]">
              p {Number(row.probability ?? 0).toFixed(2)}
            </div>
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  /* ── tactician ───────────────────────────────────────────────────────── */

  SituationRead: (d, { accent }) => (
    <div className="space-y-3">
      <Hero accent={accent}>{d.game_being_played}</Hero>
      <Fields
        items={[
          ["under pressure", d.tempo?.who_is_under_pressure],
          ["whose clock", d.tempo?.whose_clock_is_running],
          ["if you wait", d.tempo?.if_i_wait],
          [
            "misreads the game",
            (d.who_thinks_otherwise ?? []).length > 0 ? (
              <Bullets
                items={(d.who_thinks_otherwise ?? []).map(
                  (m: Data) => `${m.actor}: thinks it is ${m.thinks_the_game_is}`,
                )}
              />
            ) : null,
          ],
          [
            "information gaps",
            (d.information_asymmetries ?? []).length > 0 ? (
              <ul className="space-y-1">
                {(d.information_asymmetries ?? []).map((a: Data, index: number) => (
                  <li key={index} className="text-[13px]">
                    <span className="text-[var(--color-muted)]">{a.holder}</span> knows{" "}
                    {a.what_they_know}
                    {a.exploitable && (
                      <span className="ml-1.5 align-middle">
                        <Chip colour="var(--color-assumed)">usable</Chip>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            ) : null,
          ],
        ]}
      />
    </div>
  ),

  OptionSet: (d) => (
    <div className="space-y-2">
      <div className="text-[11.5px] text-[var(--color-faint)]">
        {(d.options ?? []).length} options generated before any evaluation.
      </div>
      <Table head={["", "option", "kind"]}>
        {(d.options ?? []).map((option: Data) => (
          <Row key={option.id} id={option.id}>
            <Cell width="52px">
              <RowId id={option.id} />
            </Cell>
            <Cell>
              <span className="font-medium">{option.label}</span>
              {option.description && (
                <div className="text-[12px] text-[var(--color-muted)]">{option.description}</div>
              )}
            </Cell>
            <Cell width="150px">
              <span className="flex flex-wrap gap-1">
                {(option.tags ?? []).map((tag: string) => (
                  <Chip key={tag} colour={TAG_COLOUR[tag]}>
                    {tag}
                  </Chip>
                ))}
              </span>
            </Cell>
          </Row>
        ))}
      </Table>
    </div>
  ),

  AsymmetryTable: (d, { accent }) => (
    <Table
      head={["option", "downside", "upside", "undo", { label: "ratio", align: "right" }]}
    >
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.option_id} id={row.option_id}>
          <Cell width="66px">
            <RowId id={row.option_id} />
            {row.time_to_know && (
              <div className="text-[10.5px] text-[var(--color-faint)]">{row.time_to_know}</div>
            )}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">
            {row.max_downside}
            <div className="mt-1">
              <Pips value={row.downside_cost ?? 0} colour="var(--color-speculative)" />
            </div>
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">
            {row.realistic_upside}
            <div className="mt-1">
              <Pips value={row.upside_value ?? 0} colour="var(--color-given)" />
            </div>
          </Cell>
          <Cell width="118px">
            <Reversibility value={row.reversibility} />
          </Cell>
          <Cell align="right" width="52px">
            <span className="mono text-[13px]" style={{ color: accent }}>
              {Number(row.ratio ?? 0).toFixed(2)}
            </span>
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  RankedOptions: (d, { accent }) => (
    <div className="space-y-3">
      <Table head={[{ label: "#", align: "left" }, "option", "why"]}>
        {(d.ranking ?? []).map((row: Data) => (
          <Row key={row.option_id} id={row.option_id}>
            <Cell width="34px">
              <span className="mono text-[13px]" style={{ color: row.rank === 1 ? accent : undefined }}>
                {row.rank}
              </span>
            </Cell>
            <Cell width="72px">
              <RowId id={row.option_id} />
            </Cell>
            <Cell className="text-[12.5px] text-[var(--color-muted)]">{row.rationale}</Cell>
          </Row>
        ))}
      </Table>
      {(d.dropped ?? []).length > 0 && (
        <div>
          <Label className="mb-1">dropped, with reasons</Label>
          <Bullets items={(d.dropped ?? []).map((x: Data) => `${x.option_id}: ${x.why}`)} />
        </div>
      )}
    </div>
  ),

  UnexpectedMove: (d, { accent }) => {
    const ethics = d.ethics_check ?? {};
    const breaches = ["uses_deception", "manufactures_urgency", "exploits_crisis"].filter(
      (key) => ethics[key],
    );
    return (
      <div className="space-y-3">
        <Hero accent={accent}>{d.move}</Hero>
        <Fields
          items={[
            ["why available", d.why_available],
            ["what it forces", d.what_it_forces],
            ["cost if wrong", d.cost_if_wrong],
          ]}
        />
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="label">influence boundary</span>
          {breaches.length === 0 ? (
            <Chip colour="var(--color-given)" title={ethics.rationale}>
              inside the boundary
            </Chip>
          ) : (
            breaches.map((key) => (
              <Chip key={key} colour="var(--color-speculative)">
                {key.replace(/_/g, " ")}
              </Chip>
            ))
          )}
        </div>
      </div>
    );
  },

  ReactionForecast: (d) => (
    <Table head={["actor", "you move", "they respond", "you then", { label: "p", align: "right" }]}>
      {(d.rows ?? []).map((row: Data, index: number) => (
        <Row key={index}>
          <Cell width="92px" className="text-[12px] text-[var(--color-muted)]">
            {row.actor}
          </Cell>
          <Cell className="text-[12px]">{row.my_move}</Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">
            {row.their_likely_response}
            {row.tempo_effect && (
              <div className="text-[11px] text-[var(--color-faint)]">{row.tempo_effect}</div>
            )}
          </Cell>
          <Cell className="text-[12px]">{row.my_counter}</Cell>
          <Cell align="right" width="42px" className="mono text-[11px] text-[var(--color-faint)]">
            {Number(row.probability ?? 0).toFixed(2)}
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  /* ── strategist ──────────────────────────────────────────────────────── */

  ActorList: (d) => (
    <Table head={["", "actor", "role"]}>
      {(d.actors ?? []).map((actor: Data) => (
        <Row key={actor.id} id={actor.id}>
          <Cell width="52px">
            <RowId id={actor.id} />
          </Cell>
          <Cell>
            {actor.label}
            {actor.is_user && (
              <span className="ml-1.5 align-middle">
                <Chip>you</Chip>
              </span>
            )}
            {actor.inferred && (
              <span className="ml-1.5 align-middle">
                <Chip colour="var(--color-assumed)" title="Not named by you — a role label">
                  inferred
                </Chip>
              </span>
            )}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">{actor.role}</Cell>
        </Row>
      ))}
    </Table>
  ),

  StakeholderGraph: (d, { accent }) => <StakeholderGraph data={d} accent={accent} />,

  IncentiveTable: (d) => (
    <Table head={["actor", "rewarded for", "will not say", { label: "clash", align: "right" }]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.actor_id} id={row.actor_id}>
          <Cell width="92px" className="text-[12px]">
            {row.actor_id}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">
            {row.rewarded_for}
            {row.punished_for && (
              <div className="text-[11.5px] text-[var(--color-faint)]">
                punished for: {row.punished_for}
              </div>
            )}
          </Cell>
          <Cell className="text-[12.5px]">{row.will_never_say}</Cell>
          <Cell align="right" width="66px">
            <Pips value={row.severity ?? 0} colour="var(--color-assumed)" />
            {row.misalignment_with_me && (
              <div className="mt-0.5 text-[11px] text-[var(--color-faint)]">
                {row.misalignment_with_me}
              </div>
            )}
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  LeverageInventory: (d, { accent }) => (
    <div className="space-y-3">
      {(d.i_control ?? []).length > 0 && (
        <>
          <Label>what you hold</Label>
          <Table head={["", "leverage", "wanted by", "expires"]}>
            {(d.i_control ?? []).map((item: Data) => (
              <Row key={item.id} id={item.id}>
                <Cell width="48px">
                  <RowId id={item.id} />
                </Cell>
                <Cell>
                  {item.what}
                  <div className="mt-1">
                    <Meter value={item.strength ?? 0} colour={accent} width={34} />
                  </div>
                </Cell>
                <Cell className="text-[12px] text-[var(--color-muted)]">{item.who_wants_it}</Cell>
                <Cell className="text-[12px] text-[var(--color-assumed)]">{item.expiry}</Cell>
              </Row>
            ))}
          </Table>
        </>
      )}
      <Fields
        items={[
          [
            "your BATNA",
            d.my_batna ? (
              <span>
                {d.my_batna.description}
                <span className="ml-2 align-middle">
                  <Meter value={d.my_batna.strength ?? 0} colour="var(--color-faint)" width={34} />
                </span>
                {d.my_batna.honest_assessment && (
                  <div className="text-[12px] text-[var(--color-faint)]">
                    {d.my_batna.honest_assessment}
                  </div>
                )}
              </span>
            ) : null,
          ],
          [
            "their BATNA",
            (d.their_batna ?? []).length > 0 ? (
              <Bullets
                items={(d.their_batna ?? []).map((b: Data) => `${b.actor_id}: ${b.description}`)}
              />
            ) : null,
          ],
        ]}
      />
    </div>
  ),

  HiddenDynamics: (d) => (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="label">confidence in this stage</span>
        <Meter value={d.confidence ?? 0} colour="var(--color-assumed)" />
        <Chip colour="var(--color-assumed)" title="Capped at 0.6 without direct evidence">
          inference
        </Chip>
      </div>
      <Fields
        items={[
          [
            "debts",
            (d.debts ?? []).length > 0 ? (
              <Bullets
                items={(d.debts ?? []).map(
                  (x: Data) =>
                    `${x.who_owes} owes ${x.owed_to} for ${x.for_what}${x.callable_now ? " (callable now)" : ""}`,
                )}
              />
            ) : null,
          ],
          [
            "alliances",
            (d.alliances ?? []).length > 0 ? (
              <Bullets
                items={(d.alliances ?? []).map(
                  (x: Data) => `${(x.members ?? []).join(" + ")} — ${x.basis}`,
                )}
              />
            ) : null,
          ],
          [
            "power shifts coming",
            (d.upcoming_shifts ?? []).length > 0 ? (
              <Bullets
                items={(d.upcoming_shifts ?? []).map(
                  (x: Data) => `${x.event} (${x.when}) — ${x.who_gains} gains, ${x.who_loses} loses`,
                )}
              />
            ) : null,
          ],
        ]}
      />
    </div>
  ),

  SequencePlan: (d, { accent }) => (
    <ol className="space-y-2.5">
      {(d.steps ?? []).map((step: Data) => (
        <li key={step.order} className="flex gap-3">
          <span
            className="mono mt-[1px] shrink-0 text-[12px]"
            style={{ color: step.commit_point ? "var(--color-speculative)" : accent }}
          >
            {String(step.order).padStart(2, "0")}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[13px]">
              <span className="text-[var(--color-muted)]">{step.actor_id}</span> — {step.objective}
              {step.commit_point && (
                <span className="ml-1.5 align-middle">
                  <Chip colour="var(--color-speculative)" title="After this, retreat is expensive">
                    commit point
                  </Chip>
                </span>
              )}
            </div>
            {step.must_yield_before_next && (
              <div className="text-[12px] text-[var(--color-faint)]">
                must yield: {step.must_yield_before_next}
              </div>
            )}
            {step.if_it_fails && (
              <div className="text-[12px] text-[var(--color-muted)]">
                if it fails: {step.if_it_fails}
              </div>
            )}
          </div>
        </li>
      ))}
    </ol>
  ),

  /* ── psychologist ────────────────────────────────────────────────────── */

  PersonList: (d) => (
    <Table head={["", "person", "relationship"]}>
      {(d.people ?? []).map((person: Data) => (
        <Row key={person.id} id={person.id}>
          <Cell width="52px">
            <RowId id={person.id} />
          </Cell>
          <Cell>
            {person.label}
            {person.is_user && (
              <span className="ml-1.5 align-middle">
                <Chip>you</Chip>
              </span>
            )}
            {person.inferred && (
              <span className="ml-1.5 align-middle">
                <Chip colour="var(--color-assumed)">inferred</Chip>
              </span>
            )}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">
            {person.relationship_to_user}
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  PersonProfileSet: (d, { accent }) => <ProfileSet data={d} accent={accent} />,

  SelfRead: (d, { accent }) => (
    <div className="space-y-3">
      <Hero accent={accent}>{d.question_behind_the_question}</Hero>
      <Fields
        items={[
          ["you said you feel", d.stated_feeling],
          ["probably feel", <span className="text-[var(--color-text)]">{d.likely_real_feeling}</span>],
          ["avoiding", d.what_is_being_avoided],
          [
            "read from your words",
            (d.evidence_from_phrasing ?? []).length > 0 ? (
              <div className="space-y-1">
                {(d.evidence_from_phrasing ?? []).map((quote: string, index: number) => (
                  <div key={index}>
                    <Quote>{quote}</Quote>
                  </div>
                ))}
              </div>
            ) : null,
          ],
          ["confidence", <Meter value={d.confidence ?? 0} colour={accent} />],
        ]}
      />
    </div>
  ),

  RelationshipEdges: (d) => (
    <Table head={["between", "dynamic", { label: "tension", align: "right" }]}>
      {(d.edges ?? []).map((edge: Data, index: number) => (
        <Row key={index}>
          <Cell width="130px" className="text-[12px] text-[var(--color-muted)]">
            {edge.a} ↔ {edge.b}
          </Cell>
          <Cell className="text-[12.5px]">
            {edge.dynamic}
            {edge.who_holds_emotional_leverage && (
              <div className="text-[11.5px] text-[var(--color-faint)]">
                leverage: {edge.who_holds_emotional_leverage}
              </div>
            )}
          </Cell>
          <Cell align="right" width="60px">
            <Pips value={edge.tension ?? 0} colour="var(--color-speculative)" />
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  ConversationScripts: (d, { accent }) => (
    <div className="space-y-3">
      {(d.scripts ?? []).map((script: Data, index: number) => (
        <div key={index} className="rounded border border-[var(--color-line-soft)] p-3">
          <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
            <span className="text-[12.5px] font-medium" style={{ color: accent }}>
              to {script.person_id}
            </span>
            <span className="text-[11.5px] text-[var(--color-faint)]">{script.goal}</span>
          </div>
          <div className="border-l-2 pl-3" style={{ borderColor: `${accent}66` }}>
            <Quote>{script.opening}</Quote>
          </div>
          {script.likely_objection && (
            <div className="mt-2 space-y-1 text-[12.5px]">
              <div className="text-[var(--color-muted)]">
                <span className="label mr-1.5">they say</span>
                {script.likely_objection}
              </div>
              {script.response && (
                <div>
                  <span className="label mr-1.5">you say</span>
                  {script.response}
                </div>
              )}
            </div>
          )}
          {script.what_not_to_say && (
            <div className="mt-2 text-[12px] text-[var(--color-speculative)]">
              <span className="label mr-1.5">do not say</span>
              {script.what_not_to_say}
            </div>
          )}
        </div>
      ))}
    </div>
  ),

  EmotionalCostTable: (d) => (
    <Table head={["option", { label: "to you", align: "right" }, "to others", "recovery"]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.option_id} id={row.option_id}>
          <Cell width="86px">
            <RowId id={row.option_id} />
          </Cell>
          <Cell align="right" width="66px">
            <Pips value={row.cost_to_me ?? 0} colour="var(--color-speculative)" />
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">
            {(row.cost_to_others ?? [])
              .map((c: Data) => `${c.person_id} ${c.cost}/5`)
              .join(" · ") || "—"}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-faint)]">{row.recovery_time}</Cell>
        </Row>
      ))}
    </Table>
  ),

  /* ── optimizer ───────────────────────────────────────────────────────── */

  OutcomeDefinition: (d, { accent }) => (
    <div className="space-y-3">
      <Hero accent={accent}>{d.outcome}</Hero>
      <Fields
        items={[
          ["metric", d.metric],
          ["deadline", d.deadline],
          ["how you would know", d.how_we_would_know],
        ]}
      />
    </div>
  ),

  WasteAudit: (d) => (
    <Table head={["", "activity", "costs", "verdict"]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.id} id={row.id}>
          <Cell width="48px">
            <RowId id={row.id} />
          </Cell>
          <Cell>
            {row.activity}
            {row.outcome_produced && (
              <div className="text-[12px] text-[var(--color-faint)]">
                produces: {row.outcome_produced}
              </div>
            )}
            {row.rationale && (
              <div className="text-[12px] text-[var(--color-muted)]">{row.rationale}</div>
            )}
          </Cell>
          <Cell width="96px" className="mono text-[12px] text-[var(--color-muted)]">
            {row.cost}
          </Cell>
          <Cell width="86px">
            <Chip colour={VERDICT_COLOUR[row.verdict]}>{row.verdict}</Chip>
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  ConstraintAnalysis: (d, { accent }) => (
    <div className="space-y-3">
      <div>
        <Label className="mb-1">the one thing limiting the outcome</Label>
        <Hero accent={accent}>{d.binding_constraint}</Hero>
      </div>
      <Fields
        items={[
          ["if relieved", d.if_relieved],
          ["evidence", (d.evidence ?? []).length > 0 ? <Bullets items={d.evidence} /> : null],
          [
            "looks binding but is not",
            (d.non_constraints ?? []).length > 0 ? (
              <Bullets
                items={(d.non_constraints ?? []).map(
                  (x: Data) => `${x.what} — ${x.why_it_looks_binding}`,
                )}
              />
            ) : null,
          ],
        ]}
      />
    </div>
  ),

  SimplestPath: (d, { accent }) => (
    <div className="space-y-3">
      <Fields
        items={[
          [
            "if you do nothing",
            d.do_nothing_baseline ? (
              <span>
                {d.do_nothing_baseline.what_happens}
                {d.do_nothing_baseline.cost && (
                  <span className="text-[var(--color-faint)]"> — {d.do_nothing_baseline.cost}</span>
                )}
                <span className="ml-1.5 align-middle">
                  <Chip
                    colour={
                      d.do_nothing_baseline.acceptable
                        ? "var(--color-given)"
                        : "var(--color-speculative)"
                    }
                  >
                    {d.do_nothing_baseline.acceptable ? "acceptable" : "not acceptable"}
                  </Chip>
                </span>
              </span>
            ) : null,
          ],
          ["simplest that works", <span className="text-[var(--color-text)]">{d.simplest_sufficient}</span>],
          ["with a tenth of the time", d.one_tenth_time_version],
          [
            "what that drops",
            (d.what_gets_dropped ?? []).length > 0 ? (
              <Bullets items={d.what_gets_dropped} colour="var(--color-speculative)" />
            ) : null,
          ],
        ]}
      />
    </div>
  ),

  EffortReturnRanking: (d, { accent }) => (
    <Table
      head={[
        "option",
        { label: "effort", align: "right" },
        { label: "return", align: "right" },
        { label: "ratio", align: "right" },
        "smaller version",
      ]}
    >
      {[...(d.rows ?? [])]
        .sort((a: Data, b: Data) => Number(b.ratio ?? 0) - Number(a.ratio ?? 0))
        .map((row: Data) => (
          <Row key={row.option_id} id={row.option_id}>
            <Cell width="92px">
              <RowId id={row.option_id} />
            </Cell>
            <Cell align="right" width="64px">
              <Pips value={row.effort ?? 0} colour="var(--color-assumed)" />
            </Cell>
            <Cell align="right" width="64px">
              <Pips value={row.expected_return ?? 0} colour="var(--color-given)" />
            </Cell>
            <Cell align="right" width="52px">
              <span className="mono text-[13px]" style={{ color: accent }}>
                {Number(row.ratio ?? 0).toFixed(2)}
              </span>
            </Cell>
            <Cell className="text-[12px] text-[var(--color-muted)]">
              {row.simpler_version || "—"}
            </Cell>
          </Row>
        ))}
    </Table>
  ),

  SystemDesign: (d, { accent }) => (
    <div className="space-y-3">
      <div>
        <Label className="mb-1">the rule that ends this decision</Label>
        <Hero accent={accent}>{d.rule}</Hero>
      </div>
      <Fields
        items={[
          ["triggered by", d.trigger],
          ["automation", d.automation],
          ["upkeep", d.maintenance_cost],
        ]}
      />
    </div>
  ),

  /* ── ethicist ────────────────────────────────────────────────────────── */

  AffectedParties: (d) => (
    <Table head={["", "party", "present", "can consent"]}>
      {(d.parties ?? []).map((party: Data) => (
        <Row key={party.id} id={party.id}>
          <Cell width="80px">
            <RowId id={party.id} />
          </Cell>
          <Cell>
            {party.label}
            {party.future_self && (
              <span className="ml-1.5 align-middle">
                <Chip colour="var(--color-inferred)">future you</Chip>
              </span>
            )}
          </Cell>
          <Cell width="90px">
            {party.in_the_room ? (
              <span className="text-[12px] text-[var(--color-muted)]">in the room</span>
            ) : (
              <Chip colour="var(--color-assumed)">not in the room</Chip>
            )}
          </Cell>
          <Cell width="96px" className="text-[12px] text-[var(--color-faint)]">
            {party.can_consent ? "yes" : "no"}
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  ValueAudit: (d) => (
    <Table head={["", "value", "source", "serves / violates"]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.id} id={row.id}>
          <Cell width="48px">
            <RowId id={row.id} />
          </Cell>
          <Cell>
            {row.value}
            {row.quote && (
              <div className="mt-0.5">
                <Quote>{row.quote}</Quote>
              </div>
            )}
          </Cell>
          <Cell width="126px">
            <Chip colour={VALUE_SOURCE_COLOUR[row.source]}>{row.source.replace(/_/g, " ")}</Chip>
          </Cell>
          <Cell className="mono text-[11.5px]">
            {(row.options_serving ?? []).length > 0 && (
              <div style={{ color: "var(--color-given)" }}>+ {(row.options_serving ?? []).join(", ")}</div>
            )}
            {(row.options_violating ?? []).length > 0 && (
              <div style={{ color: "var(--color-speculative)" }}>
                − {(row.options_violating ?? []).join(", ")}
              </div>
            )}
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  HarmLedger: (d) => (
    <Table head={["option", "who pays", { label: "size", align: "right" }, "undo", "avoidable by"]}>
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.option_id} id={row.option_id}>
          <Cell width="92px">
            <RowId id={row.option_id} />
          </Cell>
          <Cell className="text-[12px]">
            {(row.who_pays ?? []).join(", ") || "—"}
            {!row.consented && (row.who_pays ?? []).length > 0 && (
              <span className="ml-1.5 align-middle">
                <Chip colour="var(--color-assumed)">did not consent</Chip>
              </span>
            )}
          </Cell>
          <Cell align="right" width="62px">
            <Pips value={row.magnitude ?? 0} colour="var(--color-speculative)" />
          </Cell>
          <Cell width="82px" className="text-[11.5px] text-[var(--color-faint)]">
            {row.reversible ? "reversible" : "permanent"}
          </Cell>
          <Cell className="text-[12px] text-[var(--color-muted)]">
            {row.alternative_that_avoids || "—"}
          </Cell>
        </Row>
      ))}
    </Table>
  ),

  RegretMatrix: (d) => (
    <Table
      head={[
        "option",
        { label: "1y", align: "right" },
        { label: "5y", align: "right" },
        { label: "10y", align: "right" },
        "tell a friend",
      ]}
    >
      {(d.rows ?? []).map((row: Data) => (
        <Row key={row.option_id} id={row.option_id}>
          <Cell width="92px">
            <RowId id={row.option_id} />
            {row.asymmetry && (
              <div className="text-[11px] text-[var(--color-faint)]">{row.asymmetry}</div>
            )}
          </Cell>
          {(["regret_1y", "regret_5y", "regret_10y"] as const).map((key) => (
            <Cell key={key} align="right" width="52px">
              <Pips value={row[key] ?? 0} colour="var(--color-speculative)" />
            </Cell>
          ))}
          <Cell className="text-[12px] text-[var(--color-muted)]">{row.tell_a_friend_test}</Cell>
        </Row>
      ))}
    </Table>
  ),

  IntegrityCheck: (d) => (
    <Fields
      items={[
        [
          "would require becoming",
          (d.requires_becoming ?? []).length > 0 ? (
            <Bullets
              items={(d.requires_becoming ?? []).map(
                (x: Data) =>
                  `${x.option_id}: ${x.what_kind_of_person}${x.acceptable ? "" : " — not acceptable"}`,
              )}
            />
          ) : null,
        ],
        [
          "promises at stake",
          (d.promises_broken ?? []).length > 0 ? (
            <Bullets
              items={(d.promises_broken ?? []).map(
                (x: Data) =>
                  `to ${x.to_whom}: ${x.what}${x.renegotiable ? " (renegotiable)" : " (not renegotiable)"}`,
              )}
            />
          ) : null,
        ],
      ]}
    />
  ),

  InactionHarm: (d) => (
    <Fields
      items={[
        ["harm of delay", d.harm_of_delay],
        ["harm of the status quo", <span className="text-[var(--color-text)]">{d.harm_of_status_quo}</span>],
        ["who pays for inaction", (d.who_pays_for_inaction ?? []).join(", ")],
        ["what decays", d.decay],
      ]}
    />
  ),
};

/* ────────────────────────────────────────────────────────────── fallback ── */

function Generic({ data }: { data: Data }) {
  const entries = Object.entries(data).filter(([key]) => key !== "notes");
  return (
    <Fields
      items={entries.map(([key, value]) => [
        key.replace(/_/g, " "),
        Array.isArray(value) ? (
          <Bullets items={value.map((item) => (typeof item === "string" ? item : JSON.stringify(item)))} />
        ) : typeof value === "object" && value !== null ? (
          <pre className="mono overflow-x-auto text-[11.5px] text-[var(--color-muted)]">
            {JSON.stringify(value, null, 2)}
          </pre>
        ) : (
          String(value ?? "")
        ),
      ])}
    />
  );
}

export function ArtifactBody({ artifact, accent }: { artifact: Artifact; accent: string }) {
  const render = RENDERERS[artifact.kind];
  return (
    <div>
      {render ? render(artifact.data, { accent }) : <Generic data={artifact.data} />}
      {artifact.notes && (
        <div className="mt-2 border-t border-[var(--color-line-soft)] pt-2 text-[12px] italic text-[var(--color-muted)]">
          {artifact.notes}
        </div>
      )}
    </div>
  );
}

export const hasRenderer = (kind: string) => kind in RENDERERS;
