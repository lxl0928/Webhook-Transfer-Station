import js from "@eslint/js";
import ts from "typescript-eslint";
import vue from "eslint-plugin-vue";

export default ts.config(
  { ignores: ["dist/**", "node_modules/**"] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...vue.configs["flat/recommended"],
  {
    files: ["**/*.vue"],
    languageOptions: {
      globals: {
        sessionStorage: "readonly",
        window: "readonly",
        document: "readonly",
        URL: "readonly",
        HTMLElement: "readonly",
        HTMLButtonElement: "readonly",
        ResizeObserver: "readonly",
        PointerEvent: "readonly",
        MouseEvent: "readonly",
        setInterval: "readonly",
        clearInterval: "readonly",
      },
      parserOptions: { parser: ts.parser },
    },
  },
  {
    rules: {
      "vue/multi-word-component-names": "off",
      "vue/max-attributes-per-line": "off",
      "vue/html-self-closing": "off",
      "vue/singleline-html-element-content-newline": "off",
    },
  },
);
