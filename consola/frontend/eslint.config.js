import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // `types.gen.ts` se genera desde el backend (`npm run gen:types`); no se lint-ea.
  { ignores: ["dist", "../src/keni_consola/webapp", "src/types.gen.ts"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    files: ["**/*.config.{js,ts}", "**/*.test.{ts,tsx}", "src/test/**"],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
  // GUARD del Design System (ver docs/design-system.md): prohíbe REINVENTAR la píldora de
  // estado / el callout con color inline (`bg-{emerald|amber|sky|red|rose}-{400|500}/{10|15|20}`).
  // El estado se pinta con `ChipEstado`, `Badge variant="ok|info|aviso|error"` o `<Aviso>`.
  // El `ignores` es el allowlist: las primitivas que IMPLEMENTAN esos colores, las gráficas de
  // métricas, el editor (lienzo gráfico), el diff de prosa, y los mapas de color de estado
  // localizados ya existentes (feed/etapas, piezas, Pipelines) — grandfathered.
  {
    files: ["src/pages/**/*.{ts,tsx}", "src/components/**/*.{ts,tsx}"],
    ignores: [
      "**/*.test.{ts,tsx}",
      "src/components/ui/badge.tsx",
      "src/components/comunes/ChipEstado.tsx",
      "src/components/comunes/Aviso.tsx",
      "src/components/layout/ControlContexto.tsx",
      "src/components/prompts/DiffProsa.tsx",
      "src/pages/metricas/**",
      "src/pages/feed/TarjetaEtapa.tsx",
      "src/pages/piezas/meta.ts",
      "src/pages/piezas/VistaCalendario.tsx",
      "src/pages/Pipelines.tsx",
    ],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          selector:
            "Literal[value=/bg-(emerald|amber|sky|red|rose)-(400|500)\\/(10|15|20)/]",
          message:
            'No reinventes la píldora de estado / el callout con color inline. Usa ChipEstado, Badge variant="ok|info|aviso|error" o <Aviso>. Ver docs/design-system.md.',
        },
        {
          selector:
            "TemplateElement[value.cooked=/bg-(emerald|amber|sky|red|rose)-(400|500)\\/(10|15|20)/]",
          message:
            'No reinventes la píldora de estado / el callout con color inline. Usa ChipEstado, Badge variant="ok|info|aviso|error" o <Aviso>. Ver docs/design-system.md.',
        },
      ],
    },
  },
);
