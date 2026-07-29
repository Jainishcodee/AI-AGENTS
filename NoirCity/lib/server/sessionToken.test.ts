import { describe, expect, it } from "vitest";
import { signSession, verifySession, type SessionPayload } from "./sessionToken";
import { indexCase, parseCase } from "@/lib/engine/caseSchema";
import { initialState } from "@/lib/engine/reducer";
import quietRoom from "@/cases/case-00-the-quiet-room/case.json";

/**
 * Solo sessions moved out of server memory and into a token the player carries,
 * so that a Cloudflare Worker isolate being torn down between requests does not
 * lose the game. That only holds if the token cannot be edited.
 */

const caseIndex = indexCase(parseCase(quietRoom));

function fresh(): SessionPayload {
  return {
    caseId: "the-quiet-room",
    state: initialState(caseIndex),
    feed: [],
  };
}

describe("session tokens", () => {
  it("round-trips a game unchanged", async () => {
    const payload = fresh();
    payload.state.timeRemaining = 17;
    payload.state.discoveredClues = ["c_body", "c_teacup"];

    const restored = await verifySession(await signSession(payload));
    expect(restored).toEqual(payload);
  });

  it("rejects a token whose payload was edited", async () => {
    const token = await signSession(fresh());
    const [body, signature] = token.split(".");

    // Award ourselves a thousand hours - the obvious attack.
    const decoded = JSON.parse(
      Buffer.from(body, "base64url").toString("utf8"),
    ) as SessionPayload;
    decoded.state.timeRemaining = 1000;
    const forged = Buffer.from(JSON.stringify(decoded)).toString("base64url");

    expect(await verifySession(`${forged}.${signature}`)).toBeNull();
  });

  it("rejects a token whose signature was edited", async () => {
    const token = await signSession(fresh());
    const [body, signature] = token.split(".");
    // Flip an early character. The LAST base64url character of a 32-byte digest
    // carries only two significant bits, so editing it can decode to the very
    // same bytes and prove nothing.
    const flipped =
      (signature[0] === "A" ? "B" : "A") + signature.slice(1);

    expect(flipped).not.toBe(signature);
    expect(await verifySession(`${body}.${flipped}`)).toBeNull();
  });

  it("rejects a signature lifted from a different game", async () => {
    const mine = await signSession(fresh());

    const other = fresh();
    other.state.timeRemaining = 999;
    const theirs = await signSession(other);

    // Splice their body onto my signature, and vice versa.
    expect(
      await verifySession(`${theirs.split(".")[0]}.${mine.split(".")[1]}`),
    ).toBeNull();
  });

  it("rejects junk without throwing", async () => {
    for (const junk of ["", ".", "abc", "a.b", "....", "%%%.%%%"]) {
      expect(await verifySession(junk)).toBeNull();
    }
  });

  it("keeps the token to a size a request can actually carry", async () => {
    const payload = fresh();
    payload.feed = Array.from({ length: 60 }, (_, seq) => ({
      seq,
      summary: `Searched somewhere with a reasonably long name. ${seq}`,
      timeSpent: 2,
      newClues: [{ id: `c_${seq}`, title: "A clue with a title of usual length" }],
      answer:
        "A witness answer of the sort this game actually writes, which runs to a couple of sentences and sometimes rather more than that.",
    }));

    const token = await signSession(payload);
    // Comfortably inside any request body limit; nowhere near a URL or cookie.
    expect(token.length).toBeLessThan(64 * 1024);
  });
});
