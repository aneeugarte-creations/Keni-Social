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

// jsdom tampoco implementa ResizeObserver, que el feed usa para medir el copy (recorte "leer más"
// en VistaPreviaRed) y el zoom (FeedZoom). Stub no-op para que montar esos componentes no casque.
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// Ni IntersectionObserver, que usa el sentinel del scroll infinito del feed (`useSentinelInfinito`).
// Stub no-op: los tests que necesitan DISPARAR la intersección stubban el suyo propio (vi.stubGlobal).
if (typeof globalThis.IntersectionObserver === "undefined") {
  globalThis.IntersectionObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
    root = null;
    rootMargin = "";
    thresholds = [];
  } as unknown as typeof IntersectionObserver;
}

// Desmonta el arbol de React tras cada test para evitar fugas entre casos.
afterEach(() => {
  cleanup();
});
