import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

// next-env.d.ts est généré par Next à chaque build : on ne le lint pas.
const config = [
  { ignores: [".next/**", "node_modules/**", "next-env.d.ts"] },
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    files: ["*.mjs", "*.ts"],
    rules: { "import/no-anonymous-default-export": "off" },
  },
];

export default config;
