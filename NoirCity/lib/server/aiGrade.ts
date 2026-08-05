import "server-only";
import type { Action } from "@/lib/engine/reducer";
import type { CaseIndex } from "@/lib/engine/caseSchema";
import {
  clamp01,
  fractionOf,
  gradeOffline,
  type Grade,
  type PointVerdict,
} from "@/lib/engine/grade";

/**
 * Marking the written half of an accusation with a model.
 *
 * Server-only, and that is the whole architecture rather than a detail: the
 * key points ARE the solution written out in plain sentences. They are what the
 * redaction layer in `lib/engine/view.ts` exists to keep away from the browser.
 * Grading has to happen where the answer already lives.
 *
 * Cloudflare Workers AI is a binding, not an endpoint - no key, no outbound
 * request, and it runs in the same worker as the rest of the game. When the
 * binding is absent, which is every local run and every test, this falls back
 * to the offline grader and says so. A case is always playable and always
 * markable; the model makes the marking better, it is not load-bearing.
 */

const MODEL = "@cf/meta/llama-3.1-8b-instruct";

/** Never let a slow model hold the accusation open. */
const TIMEOUT_MS = 8000;

interface WorkersAi {
  run: (
    model: string,
    input: Record<string, unknown>,
  ) => Promise<{ response?: string }>;
}

/**
 * The Workers AI binding, when there is one.
 *
 * OpenNext exposes Cloudflare bindings through `getCloudflareContext`. That
 * import only resolves inside the worker, so it is dynamic - importing it at
 * module scope would break `next build` and every test in this repo.
 */
async function binding(): Promise<WorkersAi | null> {
  try {
    const mod = await import("@opennextjs/cloudflare");
    const ctx = await mod.getCloudflareContext({ async: true });
    const ai = (ctx?.env as Record<string, unknown> | undefined)?.AI;
    return ai && typeof (ai as WorkersAi).run === "function"
      ? (ai as WorkersAi)
      : null;
  } catch {
    return null;
  }
}

function prompt(caseIndex: CaseIndex, argument: string): string {
  const points = caseIndex.file.solution.keyPoints
    .map((p, i) => `${i + 1}. ${p.claim}`)
    .join("\n");

  // Asked for a bare JSON array and told twice to be strict. Models grading
  // free text drift generous by default - they reward effort and confidence -
  // and a grader that gives credit for a well-written wrong answer is worse
  // than no grader, because the player learns nothing from the score.
  return `You are marking a detective's written accusation against the true solution of a case. Be strict and literal.

The true solution consists of these numbered points:
${points}

The detective wrote:
"""
${argument}
"""

For each numbered point, decide how well the detective's writing establishes THAT point. Judge meaning, not wording - they may use different words for the same idea, and that counts. But do not give credit for a point they did not make, for vague gestures, or for merely naming a thing without saying what it shows.

Score each point:
1.0 = clearly established
0.5 = partly there, or hinted without being stated
0.0 = absent, or wrong

Reply with ONLY a JSON array, one object per point, in order:
[{"i":1,"credit":1.0,"note":"one short sentence"}]

No prose before or after. No markdown fences.`;
}

/** Pulls the first JSON array out of a model's reply. */
function parseVerdicts(text: string): Array<{ i: number; credit: number; note?: string }> | null {
  const start = text.indexOf("[");
  const end = text.lastIndexOf("]");
  if (start < 0 || end <= start) return null;
  try {
    const raw: unknown = JSON.parse(text.slice(start, end + 1));
    if (!Array.isArray(raw)) return null;
    return raw
      .filter((r): r is Record<string, unknown> => typeof r === "object" && r !== null)
      .map((r) => ({
        i: Number(r.i),
        credit: Number(r.credit),
        note: typeof r.note === "string" ? r.note : undefined,
      }))
      .filter((r) => Number.isFinite(r.i) && Number.isFinite(r.credit));
  } catch {
    return null;
  }
}

/**
 * The one place an accusation picks up its mark.
 *
 * Both entry points - the solo session and the shared room - pass every action
 * through here on its way to the reducer. Only `accuse` is touched; everything
 * else goes past untouched and un-awaited beyond the promise.
 *
 * This is where the grade is attached, and it is the only place: the field is
 * absent from both API route schemas, so a grade cannot arrive from a browser.
 */
export async function withGrade(
  caseIndex: CaseIndex,
  action: Action,
): Promise<Action> {
  if (action.type !== "accuse") return action;
  return { ...action, grade: await gradeArgument(caseIndex, action.argument) };
}

export async function gradeArgument(
  caseIndex: CaseIndex,
  argument: string,
): Promise<Grade> {
  const ai = await binding();
  if (!ai) return gradeOffline(caseIndex, argument);

  try {
    const reply = await Promise.race([
      ai.run(MODEL, {
        messages: [{ role: "user", content: prompt(caseIndex, argument) }],
        // Marking is not a creative task; the same case argued the same way
        // should get the same score twice.
        temperature: 0,
        max_tokens: 600,
      }),
      new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error("grader timed out")), TIMEOUT_MS),
      ),
    ]);

    const verdicts = parseVerdicts(reply?.response ?? "");
    if (!verdicts?.length) return gradeOffline(caseIndex, argument);

    const byIndex = new Map(verdicts.map((v) => [v.i, v]));
    const points: PointVerdict[] = caseIndex.file.solution.keyPoints.map(
      (p, i) => {
        const v = byIndex.get(i + 1);
        return {
          id: p.id,
          claim: p.claim,
          credit: clamp01(v?.credit ?? 0),
          note: v?.note?.slice(0, 160) ?? null,
        };
      },
    );

    return { points, fraction: fractionOf(points), by: "model" };
  } catch (e) {
    // A grader that is down must never cost somebody their accusation - they
    // get the offline mark, and the verdict says which one they got.
    console.error("[aiGrade]", e);
    return gradeOffline(caseIndex, argument);
  }
}
