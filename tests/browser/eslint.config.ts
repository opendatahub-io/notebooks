import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import playwright from "eslint-plugin-playwright";

export default tseslint.config(
  {
    ignores: [
      "cypress/",
      "node_modules/",
      "playwright-report/",
      "results/",
      "test-results/",
      "**/*.js",
      "scripts/repro.ts",
    ],
  },
  eslint.configs.recommended,
  ...tseslint.configs.recommendedTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-unnecessary-condition": "error",
      "@typescript-eslint/no-floating-promises": "error",
      // catch (e) { throw new Error(`...${e}`) } is common and fine
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      // Allow _prefixed unused vars (destructuring, callback signatures)
      "@typescript-eslint/no-unused-vars": ["error", {
        argsIgnorePattern: "^_",
        varsIgnorePattern: "^_",
        caughtErrorsIgnorePattern: "^_",
      }],
    },
  },
  {
    // Page object model adapted from upstream code-server — relax strict typing rules
    files: ["tests/models/**/*.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unsafe-member-access": "off",
      "@typescript-eslint/restrict-template-expressions": "off",
      "@typescript-eslint/no-misused-promises": "off",
      "@typescript-eslint/await-thenable": "off",
    },
  },
  {
    // Utility scripts — not test code, relax type-aware rules
    files: ["scripts/**/*.ts"],
    rules: {
      "@typescript-eslint/no-floating-promises": "off",
      "@typescript-eslint/restrict-template-expressions": "off",
      "@typescript-eslint/no-unnecessary-condition": "off",
    },
  },
  {
    files: ["tests/**/*.spec.ts"],
    ...playwright.configs["flat/recommended"],
    rules: {
      ...playwright.configs["flat/recommended"].rules,
      // Some tests are visual/smoke — no explicit assertions needed
      "playwright/expect-expect": "warn",
    },
  },
);
