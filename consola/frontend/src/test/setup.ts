import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// jsdom no implementa estas APIs del DOM que Radix usa al abrir menus/selects
// (Select, Dropdown). Sin estos stubs, abrir un <Select> en un test lanza
// "scrollIntoView is not a function" / "hasPointerCapture is not a function".
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}

// Desmonta el arbol de React tras cada test para evitar fugas entre casos.
afterEach(() => {
  cleanup();
});
