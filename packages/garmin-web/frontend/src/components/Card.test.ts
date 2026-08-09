/**
 * @vitest-environment node
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CARD_CLASS } from "./Card";

/**
 * Single-source guard for the card shell (Issue #914).
 *
 * The class list was pasted into ~25 components, so "make the cards a little
 * flatter" was a 25-file edit that nobody ever completed consistently. Only
 * `Card.ts` may spell the shell out; everything else imports `CARD_CLASS`.
 */

const SRC_DIR = fileURLToPath(new URL("../", import.meta.url));

/**
 * The shell's identifying prefix, assembled at runtime so this guard is not
 * itself an occurrence of the string it bans.
 */
const CARD_LITERAL = [
  "rounded-xl",
  "border",
  "border-slate-200",
  "bg-white",
  "p-5",
].join(" ");

/** Every checked-in TS/TSX source file under `src/`. */
function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      return sourceFiles(full);
    }
    return /\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

describe("CARD_CLASS", () => {
  it("test_card_class_single_source", () => {
    // The constant is the definition the guard is protecting.
    expect(CARD_CLASS).toContain(CARD_LITERAL);

    const offenders = sourceFiles(SRC_DIR)
      .filter((file) => readFileSync(file, "utf8").includes(CARD_LITERAL))
      .map((file) => relative(SRC_DIR, file).split(sep).join("/"))
      .sort();

    expect(offenders).toEqual(["components/Card.ts"]);
  });
});
