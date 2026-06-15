/**
 * PanelVersiones para un equipo de redes NO técnico: comparación «Tu borrador ↔ versión
 * elegida», fila sintética del borrador, lista de PUBLICACIONES por su nota (sin SHA), la
 * que está EN VIVO marcada, diff ancho «Revisar cambios», acciones VISIBLES por fila
 * («Abrir versión», «Restaurar») y «Descartar cambios».
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PanelVersiones } from "./PanelVersiones";

// Confirmación: auto-acepta (el contenedor visual no se monta en este test).
vi.mock("@/components/comunes/confirmar", () => ({
  confirmar: vi.fn(async () => true),
}));

const HISTORIAL = [
  {
    sha: "aaa111",
    sha_corto: "aaa111a",
    fecha: "2026-06-10T10:00:00",
    autor: "ana",
    mensaje: "Tono más directo en titulares",
  },
  {
    sha: "bbb222",
    sha_corto: "bbb222b",
    fecha: "2026-06-01T09:00:00",
    autor: "luis",
    mensaje: "Primera versión de la voz",
  },
];

function json(body: unknown, status = 200) {
  return Promise.resolve(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function stubFetch() {
  const llamadas: { path: string; metodo: string }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string | URL, init?: RequestInit) => {
      const path = new URL(String(url), "http://localhost").pathname;
      const metodo = (init?.method ?? "GET").toUpperCase();
      llamadas.push({ path, metodo });
      if (path.endsWith("/historial")) return json({ historial: HISTORIAL });
      if (path.endsWith("/descartar"))
        return json({ documento: { id: "doc", cuerpo: "Publicado" } });
      if (path.includes("/revertir/"))
        return json({ documento: { id: "doc", cuerpo: "Texto publicado." } });
      if (path.includes("/version/"))
        return json({ documento: { id: "doc", cuerpo: "Texto publicado." } });
      return json({ error: `sin stub: ${metodo} ${path}` }, 404);
    }),
  );
  return llamadas;
}

function montar(props: Partial<React.ComponentProps<typeof PanelVersiones>> = {}) {
  const onBorradorActualizado = props.onBorradorActualizado ?? vi.fn();
  const onPublicar = props.onPublicar ?? vi.fn();
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <PanelVersiones
        docId="editorial/rrss/unotv/voz"
        produccionSha="aaa111"
        cuerpoBorrador="Texto del borrador en edición."
        sinPublicar
        onPublicar={onPublicar}
        onBorradorActualizado={onBorradorActualizado}
        {...props}
      />
    </QueryClientProvider>,
  );
  return { onBorradorActualizado, onPublicar };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("PanelVersiones", () => {
  it("lista las publicaciones por su nota, marca EN VIVO y no muestra SHAs", async () => {
    stubFetch();
    montar();
    expect(await screen.findByText("Tono más directo en titulares")).toBeInTheDocument();
    // Aparece como fila y como opción del selector «Comparar con»; basta con que esté.
    expect(screen.getAllByText("Primera versión de la voz").length).toBeGreaterThan(0);
    expect(screen.getByText("EN VIVO")).toBeInTheDocument();
    // Fila sintética del borrador con su badge humano.
    expect(screen.getByText("Tu borrador")).toBeInTheDocument();
    expect(screen.getByText("Cambios sin publicar")).toBeInTheDocument();
    // El SHA no aparece como texto visible (solo en title/tooltip).
    expect(screen.queryByText(/aaa111/)).not.toBeInTheDocument();
  });

  it("«Revisar y publicar» dispara el flujo de publicación", async () => {
    stubFetch();
    const { onPublicar } = montar();
    fireEvent.click(await screen.findByRole("button", { name: /Revisar y publicar/ }));
    expect(onPublicar).toHaveBeenCalledTimes(1);
  });

  it("«Ver qué cambió» abre el diff ancho «Revisar cambios»", async () => {
    stubFetch();
    montar();
    fireEvent.click(await screen.findByRole("button", { name: /Ver qué cambió/ }));
    expect(await screen.findByText("Revisar cambios")).toBeInTheDocument();
    expect(screen.getByText(/Cambios desde lo publicado/)).toBeInTheDocument();
  });

  it("«Descartar cambios» llama a descartar y avisa al contenedor", async () => {
    const llamadas = stubFetch();
    const { onBorradorActualizado } = montar();
    fireEvent.click(await screen.findByRole("button", { name: /Descartar cambios/ }));
    await waitFor(() =>
      expect(llamadas.some((l) => l.metodo === "POST" && l.path.endsWith("/descartar"))).toBe(true),
    );
    await waitFor(() => expect(onBorradorActualizado).toHaveBeenCalled());
  });

  it("«Abrir versión» (botón visible) abre el lector renderizado de esa versión", async () => {
    stubFetch();
    montar();
    await screen.findByText("Tono más directo en titulares");
    // Nombre exacto: la fila también es role=button, pero su nombre es el texto completo.
    const botones = screen.getAllByRole("button", { name: "Abrir versión" });
    expect(botones.length).toBe(HISTORIAL.length);
    fireEvent.click(botones[0]);
    expect(await screen.findByText("Texto publicado.")).toBeInTheDocument();
  });

  it("«Restaurar» (botón visible) trae la versión al borrador y avisa al contenedor", async () => {
    const llamadas = stubFetch();
    const { onBorradorActualizado } = montar();
    await screen.findByText("Tono más directo en titulares");
    const botones = screen.getAllByRole("button", { name: "Restaurar" });
    expect(botones.length).toBe(HISTORIAL.length);
    fireEvent.click(botones[0]);
    await waitFor(() =>
      expect(llamadas.some((l) => l.metodo === "POST" && l.path.includes("/revertir/"))).toBe(true),
    );
    await waitFor(() => expect(onBorradorActualizado).toHaveBeenCalled());
  });

  it("abrir el diff de una fila NO cambia el selector «Comparar con»", async () => {
    stubFetch();
    montar();
    await screen.findAllByText("Primera versión de la voz");
    const selector = screen.getByLabelText(
      "Versión publicada a comparar con tu borrador",
    ) as HTMLSelectElement;
    // Por defecto el selector apunta a lo publicado (en vivo).
    expect(selector.value).toBe("aaa111");
    // Clic en el cuerpo de la 2ª publicación (su autor es único en esa fila).
    fireEvent.click(screen.getByText("luis"));
    expect(await screen.findByText("Revisar cambios")).toBeInTheDocument();
    // El diff muestra ESA versión, no la del selector…
    expect(screen.getByText(/Cambios desde esta versión/)).toBeInTheDocument();
    // …y el selector del sidebar sigue intacto.
    expect(selector.value).toBe("aaa111");
  });

  it("«Ver qué cambió» se deshabilita cuando no hay cambios sin publicar", async () => {
    stubFetch();
    montar({ sinPublicar: false });
    const boton = await screen.findByRole("button", { name: /Ver qué cambió/ });
    expect(boton).toBeDisabled();
  });
});
