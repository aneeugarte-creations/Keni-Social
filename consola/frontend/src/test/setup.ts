import "@testing-library/jest-dom/vitest";

import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Node >= 22 trae un `localStorage` NATIVO experimental que, sin `--localstorage-file`,
// es un objeto INERTE (sin setItem/clear funcionales; node avisa "--localstorage-file was
// provided without a valid path") y PISA al localStorage de jsdom en los tests. Cualquier
// test que use el localStorage real (columnas del feed, rail del sidebar) revienta con
// "setItem is not a function" — en local con node nuevo y en el CI (node:22) por igual.
// Si el ambiente está roto, instalamos una implementación EN MEMORIA equivalente.
const localStorageRoto = (() => {
  try {
    window.localStorage.setItem("__sonda_ls__", "1");
    window.localStorage.removeItem("__sonda_ls__");
    return false;
  } catch {
    return true;
  }
})();
if (localStorageRoto) {
  let almacen: Record<string, string> = {};
  const enMemoria: Storage = {
    get length() {
      return Object.keys(almacen).length;
    },
    clear: () => {
      almacen = {};
    },
    getItem: (k: string) => (k in almacen ? almacen[k] : null),
    key: (i: number) => Object.keys(almacen)[i] ?? null,
    removeItem: (k: string) => {
      delete almacen[k];
    },
    setItem: (k: string, v: string) => {
      almacen[k] = String(v);
    },
  };
  Object.defineProperty(window, "localStorage", {
    value: enMemoria,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(globalThis, "localStorage", {
    value: enMemoria,
    configurable: true,
    writable: true,
  });
}

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
// en VistaPreviaRed) y el ancho real del contenedor (columnas efectivas de FeedIdeacion). Stub
// no-op (no dispara callbacks): en esos componentes vale la medición inicial del layout-effect.
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

// Choque node<->jsdom con el data-router de react-router: al navegar construye
// `new Request(url, { signal })` con el AbortSignal GLOBAL (el de jsdom), pero la clase
// Request es la nativa de node (undici, jsdom no trae Request) y undici EXIGE su propio
// AbortSignal ("Expected signal to be an instance of AbortSignal") -> la navegacion
// revienta como unhandled rejection y el test no ve la pagina destino. En tests no se
// aborta ninguna navegacion: si el signal no es de la clase nativa, se omite.
const RequestNativa = globalThis.Request;
if (typeof RequestNativa === "function") {
  // No se puede discriminar por clase (el AbortSignal de jsdom y el nativo se confunden
  // segun el orden de carga): se intenta construir tal cual y, si undici rechaza el
  // signal, se reconstruye SIN el (en tests nadie aborta una navegacion).
  function RequestTolerante(entrada: RequestInfo | URL, init?: RequestInit) {
    try {
      return new RequestNativa(entrada, init);
    } catch (e) {
      if (init && "signal" in init) {
        return new RequestNativa(entrada, { ...init, signal: undefined });
      }
      throw e;
    }
  }
  RequestTolerante.prototype = RequestNativa.prototype; // instanceof Request sigue valiendo
  globalThis.Request = RequestTolerante as unknown as typeof Request;
}

// Desmonta el arbol de React tras cada test para evitar fugas entre casos.
afterEach(() => {
  cleanup();
});
