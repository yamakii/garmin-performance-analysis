import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import reactX from "eslint-plugin-react-x";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "coverage"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
      // eslint-plugin-react is capped at eslint ^9.7 and unmaintained since
      // 2025-04; react-x carries the one rule we use and accepts eslint 10 (#1504).
      "react-x": reactX,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Vite HMR boundary: warn (not error) so shared style/util exports
      // alongside components stay allowed where intentional.
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      // Honors the existing eslint-disable comments in the codebase.
      "react-x/no-array-index-key": "warn",
    },
  },
);
