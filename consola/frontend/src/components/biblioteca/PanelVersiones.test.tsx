/**
 * PanelVersiones para un equipo de redes NO técnico: un CTA prominente «Revisar y publicar»
 * cuando hay cambios sin publicar, una fila sintética «Tu borrador», la lista de
 * PUBLICACIONES por su nota (sin SHA) con la que está EN VIVO marcada, y por fila las
 * acciones «Ver» (diff a pantalla completa de esa versión ↔ tu borrador) y «Restaurar».
 * Ya NO hay dropdown de «Comparar con»: la comparación es por versión.
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
    expect(screen.getByText("Primera versión de la voz")).toBeInTheDocument();
    expect(screen.getByText("EN VIVO")).toBeInTheDocument();
    // Fila sintética del borrador con su badge humano.
    expect(screen.getByText("Tu borrador")).toBeInTheDocument();
    expect(screen.getByText("Cambios sin publicar")).toBeInTheDocument();
    // El SHA no aparece como texto visible (solo en title/tooltip).
    expect(screen.queryByText(/aaa111/)).not.toBeInTheDocument();
  });

  it("ya NO ofrece un dropdown «Comparar con»", async () => {
    stubFetch();
    montar();
    await screen.findByText("Tono más directo en titulares");
    expect(
      screen.queryByLabelText("Versión publicada a comparar con tu borrador"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Ver qué cambió/ })).not.toBeInTheDocument();
  });

  it("muestra el CTA «Revisar y publicar» y dispara el flujo de publicación", async () => {
    stubFetch();
    const { onPublicar } = montar();
    fireEvent.click(await screen.findByRole("button", { name: /Revisar y publicar/ }));
    expect(onPublicar).toHaveBeenCalledTimes(1);
  });

  it("oculta las acciones del borrador y marca «Al día» cuando no hay cambios sin publicar", async () => {
    stubFetch();
    montar({ sinPublicar: false });
    await screen.findByText("Tono más directo en titulares");
    expect(screen.queryByRole("button", { name: /Revisar y publicar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Descartar cambios/ })).not.toBeInTheDocument();
    expect(screen.getByText("Al día")).toBeInTheDocument();
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

  it("«Ver» abre el diff a pantalla completa de esa versión ↔ tu borrador", async () => {
    stubFetch();
    montar();
    await screen.findByText("Tono más directo en titulares");
    const botones = screen.getAllByRole("button", { name: "Ver" });
    expect(botones.length).toBe(HISTORIAL.length);
    // La 1ª publicación es la que está EN VIVO → subtítulo «desde lo publicado».
    fireEvent.click(botones[0]);
    expect(await screen.findByText(/Cambios desde lo publicado/)).toBeInTheDocument();
    // La vista de revisión a pantalla completa trae su toggle «Solo cambios».
    expect(await screen.findByLabelText("Solo cambios")).toBeInTheDocument();
  });

  it("«Ver» de una versión NO en vivo usa el subtítulo «desde esta versión»", async () => {
    stubFetch();
    montar();
    await screen.findByText("Primera versión de la voz");
    const botones = screen.getAllByRole("button", { name: "Ver" });
    fireEvent.click(botones[1]);
    expect(await screen.findByText(/Cambios desde esta versión/)).toBeInTheDocument();
  });

  it("«Restaurar» trae la versión al borrador y avisa al contenedor", async () => {
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
});
