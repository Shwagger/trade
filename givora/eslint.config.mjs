import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

// next-env.d.ts est généré par Next à chaque build : on ne le lint pas.
const config = [
  // .test-build est du JS généré par tsc pour les tests, et tests/ est
  // en CommonJS exprès (node ne résout pas les imports sans extension).
  { ignores: [".next/**", "node_modules/**", ".test-build/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    files: ["*.mjs", "*.ts"],
    rules: { "import/no-anonymous-default-export": "off" },
  },
  {
    files: ["tests/**/*.cjs"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
];

export default config;
