import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Desmonta el arbol de React tras cada test para evitar fugas entre casos.
afterEach(() => {
  cleanup();
});
