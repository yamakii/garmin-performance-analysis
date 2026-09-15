/**
 * @vitest-environment node
 */
import { readdirSync, readFileSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { CARD_CLASS } from "./Card";

/**
 * Decoration guard for the Morning Brief system (#1116, formerly the
 * single-source guard of #914).
 *
 * The system has no shadows, no large radii, no gradients, one prose face and
 * one mono face, and every color is a token. Each of those used to creep back
 * in one call site at a time, so the retired utilities are listed here and any
 * reappearance under `src/` fails the build. The patterns are assembled at
 * runtime so this file is not itself an occurrence.
 */

const SRC_DIR = fileURLToPath(new URL("../", import.meta.url));

/** Utility classes the system retired; matched as whole class tokens. */
const BANNED_TOKENS = [
  ["rounded", "xl"].join("-"),
  ["rounded", "2xl"].join("-"),
  ["rounded", "lg"].join("-"),
  ["rounded", "full"].join("-"),
  ["shadow", "sm"].join("-"),
  ["shadow", "md"].join("-"),
  ["bg", "gradient"].join("-"),
  ["font", "display"].join("-"),
  ["font", "numeric"].join("-"),
  ["status", "info"].join("-"),
];

/** Raw Tailwind palette hues (any prefix) and the retired brand tokens. */
const BANNED_HUES = ["slate", "emerald", "sky", "amber", "red", "rose"];
const BANNED_BRAND = ["signal", "gold"];

const CLASS_PREFIX =
  "(?:[a-z-]+:)*(?:text|bg|border|divide|ring|from|via|to|outline|fill|stroke)";

function bannedPatterns(): RegExp[] {
  return [
    ...BANNED_TOKENS.map((token) => new RegExp(`(?<![\\w-])${token}(?![\\w-])`)),
    new RegExp(`(?<![\\w-])${CLASS_PREFIX}-(?:${BANNED_HUES.join("|")})-\\d`),
    new RegExp(
      `(?<![\\w-])${CLASS_PREFIX}-(?:${BANNED_BRAND.join("|")})(?:-ink)?(?![\\w-])`,
    ),
  ];
}

/** Every checked-in non-test TS/TSX source file under `src/`. */
function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      return sourceFiles(full);
    }
    return /\.tsx?$/.test(entry.name) && !/\.test\./.test(entry.name)
      ? [full]
      : [];
  });
}

describe("CARD_CLASS", () => {
  it("test_card_class_single_source", () => {
    expect(CARD_CLASS).toBe("border-t border-hairline pt-4");

    // The pre-#1116 shell must not survive anywhere, spelled out or not.
    const legacy = ["rounded", "xl border border", "slate", "200"].join("-");
    const offenders = sourceFiles(SRC_DIR)
      .filter((file) => readFileSync(file, "utf8").includes(legacy))
      .map((file) => relative(SRC_DIR, file).split(sep).join("/"));

    expect(offenders).toEqual([]);
  });

  it("test_no_legacy_decoration_classes", () => {
    const patterns = bannedPatterns();
    const files = sourceFiles(SRC_DIR);
    // A scan that silently walks nothing would "pass" forever.
    expect(files.some((file) => file.endsWith("Layout.tsx"))).toBe(true);

    const offenders = files
      .flatMap((file) => {
        const text = readFileSync(file, "utf8");
        return patterns
          .filter((pattern) => pattern.test(text))
          .map(
            (pattern) =>
              `${relative(SRC_DIR, file).split(sep).join("/")}: ${pattern.source}`,
          );
      })
      .sort();

    expect(offenders).toEqual([]);
  });
});
