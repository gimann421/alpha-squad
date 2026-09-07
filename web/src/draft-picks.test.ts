import { describe, expect, it } from "vitest";
import { nextPickNumber, pickNumberOf, snakePickNumbers, withPickNumber } from "./draft-picks";

describe("pickNumberOf", () => {
  it("numbers the board 1..N in order", () => {
    const board = ["a", "b", "c"];
    expect(board.map((id) => pickNumberOf(board, id))).toEqual([1, 2, 3]);
  });

  it("returns null for a player who is not on the board", () => {
    expect(pickNumberOf(["a"], "z")).toBeNull();
  });
});

describe("withPickNumber", () => {
  it("moves a player earlier and shifts everyone between him and his old slot", () => {
    expect(withPickNumber(["a", "b", "c", "d"], "d", 2)).toEqual(["a", "d", "b", "c"]);
  });

  it("moves a player later the same way", () => {
    expect(withPickNumber(["a", "b", "c", "d"], "a", 3)).toEqual(["b", "c", "a", "d"]);
  });

  it("always leaves the numbering contiguous with no gaps or duplicates", () => {
    const board = ["a", "b", "c", "d", "e"];
    for (const target of [1, 2, 3, 4, 5]) {
      const moved = withPickNumber(board, "c", target);
      expect([...moved].sort()).toEqual([...board].sort());
      expect(moved.map((id) => pickNumberOf(moved, id))).toEqual([1, 2, 3, 4, 5]);
    }
  });

  it("clamps an out-of-range number to the first or last slot rather than doing nothing", () => {
    expect(withPickNumber(["a", "b", "c"], "c", 0)).toEqual(["c", "a", "b"]);
    expect(withPickNumber(["a", "b", "c"], "a", 99)).toEqual(["b", "c", "a"]);
  });

  it("is a no-op for an unchanged number, an unknown player, or a blank input", () => {
    expect(withPickNumber(["a", "b"], "a", 1)).toEqual(["a", "b"]);
    expect(withPickNumber(["a", "b"], "z", 1)).toEqual(["a", "b"]);
    expect(withPickNumber(["a", "b"], "a", Number.NaN)).toEqual(["a", "b"]);
  });

  it("never mutates the array it was given", () => {
    const board = ["a", "b", "c"];
    withPickNumber(board, "c", 1);
    expect(board).toEqual(["a", "b", "c"]);
  });
});

describe("snakePickNumbers", () => {
  it("reverses on even rounds", () => {
    // 10-team league, slot 3: round 1 pick 3, round 2 pick 18, round 3 pick 23, ...
    expect(snakePickNumbers(10, 4, 3)).toEqual([3, 18, 23, 38]);
  });

  it("gives slot 1 and slot N the mirrored turn pattern", () => {
    expect(snakePickNumbers(10, 3, 1)).toEqual([1, 20, 21]);
    expect(snakePickNumbers(10, 3, 10)).toEqual([10, 11, 30]);
  });

  it("produces exactly one pick per round", () => {
    expect(snakePickNumbers(12, 16, 7)).toHaveLength(16);
  });

  it("never repeats a pick number across the whole league", () => {
    const teams = 10;
    const rounds = 16;
    const all = Array.from({ length: teams }, (_, i) =>
      snakePickNumbers(teams, rounds, i + 1),
    ).flat();
    expect(new Set(all).size).toBe(teams * rounds);
    expect(Math.max(...all)).toBe(teams * rounds);
  });

  it("returns nothing for an impossible slot rather than a wrong schedule", () => {
    expect(snakePickNumbers(10, 16, 0)).toEqual([]);
    expect(snakePickNumbers(10, 16, 11)).toEqual([]);
    expect(snakePickNumbers(0, 16, 1)).toEqual([]);
  });
});

describe("nextPickNumber", () => {
  it("is the first scheduled pick beyond what has been logged", () => {
    const picks = snakePickNumbers(10, 16, 3); // 3, 18, 23, 38, ...
    expect(nextPickNumber(picks, 0)).toBe(3);
    expect(nextPickNumber(picks, 3)).toBe(18);
    expect(nextPickNumber(picks, 17)).toBe(18);
    expect(nextPickNumber(picks, 18)).toBe(23);
  });

  it("is null once the draft is over", () => {
    expect(nextPickNumber(snakePickNumbers(10, 2, 1), 100)).toBeNull();
  });
});
