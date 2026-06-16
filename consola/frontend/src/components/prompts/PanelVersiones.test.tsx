/**
 * PanelVersiones para un equipo de redes NO técnico: un CTA prominente «Revisar y publicar»
 * cuando hay cambios sin publicar, la lista de PUBLICACIONES por su nota (sin SHA) con la que
 * está EN VIVO marcada, y por versión: clic en la fila → ver ESA versión en solo lectura, y
 * «Restaurar» → revertir en un clic (publica si admin, solicita si editor). La fila sintética
 * «Tu borrador» solo aparece cuando hay cambios sin publicar.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
      if (path.endsWith("/publicar"))
        return json({ documento: { id: "doc", cuerpo: "Texto publicado." } });
      if (path.endsWith("/solicitar")) return json({ solicitud: { id: "s1" } });
      if (path.includes("/revertir/"))
        return json({ documento: { id: "doc", cuerpo: "Texto publicado." } });
      if (path.includes("/version/"))
        return json({ documento: { id: "doc", cuerpo: "Texto de esa versión." } });
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
    // Fila sintética del borrador con su badge humano (hay cambios sin publicar).
    expect(screen.getByText("Tu borrador")).toBeInTheDocument();
    expect(screen.getByText("Cambios sin publicar")).toBeInTheDocument();
    // El SHA no aparece como texto visible (solo en title/tooltip).
    expect(screen.queryByText(/aaa111/)).not.toBeInTheDocument();
  });

  it("ya NO ofrece un dropdown «Comparar con» ni un botón «Ver qué cambió»", async () => {
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

  it("sin cambios: «sin acciones» y SIN fila «Tu borrador»", async () => {
    stubFetch();
    montar({ sinPublicar: false });
    await screen.findByText("Tono más directo en titulares");
    expect(screen.queryByRole("button", { name: /Revisar y publicar/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Descartar cambios/ })).not.toBeInTheDocument();
    // La fila «Tu borrador» sobra cuando no hay cambios: no se muestra.
    expect(screen.queryByText("Tu borrador")).not.toBeInTheDocument();
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

  it("clic en una versión abre SU contenido en solo lectura (no un diff)", async () => {
    stubFetch();
    montar();
    await screen.findByText("Primera versión de la voz");
    fireEvent.click(screen.getByRole("button", { name: /Primera versión de la voz/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Primera versión de la voz")).toBeInTheDocument();
    // No es un diff: no hay toggle «Solo cambios».
    expect(screen.queryByLabelText("Solo cambios")).not.toBeInTheDocument();
  });

  // Subtítulo cronológico esperado SIEMPRE: la más antigua (1 jun) es el «antes».
  const SUBTITULO_CRONOLOGICO =
    "Cambios desde «Primera versión de la voz» hasta «Tono más directo en titulares»";

  it("comparar muestra el diff con su toggle, y el sentido es cronológico (abro la antigua)", async () => {
    stubFetch();
    montar();
    // Abro la ANTIGUA (bbb222, 1 jun) y comparo con la NUEVA (aaa111, 10 jun).
    await screen.findByText("Primera versión de la voz");
    fireEvent.click(screen.getByRole("button", { name: /Primera versión de la voz/ }));
    const dialog = await screen.findByRole("dialog");
    // Por defecto solo se ve el contenido (sin barra de diff).
    expect(within(dialog).queryByText("Solo cambios")).not.toBeInTheDocument();
    fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "aaa111" } });
    expect(await within(dialog).findByText("Solo cambios")).toBeInTheDocument();
    expect(within(dialog).getByText(SUBTITULO_CRONOLOGICO)).toBeInTheDocument();
  });

  it("el sentido del diff NO depende de cuál abras (abro la nueva, comparo con la antigua)", async () => {
    stubFetch();
    montar();
    // Abro la NUEVA (aaa111) y comparo con la ANTIGUA (bbb222) → MISMO sentido cronológico.
    await screen.findByText("Tono más directo en titulares");
    fireEvent.click(screen.getByRole("button", { name: /Tono más directo en titulares/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "bbb222" } });
    expect(await within(dialog).findByText(SUBTITULO_CRONOLOGICO)).toBeInTheDocument();
  });

  it("«Restaurar» (admin) revierte en un clic: revierte y publica", async () => {
    const llamadas = stubFetch();
    const { onBorradorActualizado } = montar({ esAdmin: true });
    await screen.findByText("Primera versión de la voz");
    // Solo la versión que NO está EN VIVO ofrece «Restaurar».
    fireEvent.click(screen.getByRole("button", { name: "Restaurar" }));
    await waitFor(() =>
      expect(llamadas.some((l) => l.metodo === "POST" && l.path.includes("/revertir/"))).toBe(true),
    );
    await waitFor(() =>
      expect(llamadas.some((l) => l.metodo === "POST" && l.path.endsWith("/publicar"))).toBe(true),
    );
    await waitFor(() => expect(onBorradorActualizado).toHaveBeenCalled());
  });

  it("«Restaurar» (editor) envía una solicitud en vez de publicar", async () => {
    const llamadas = stubFetch();
    montar({ esAdmin: false });
    await screen.findByText("Primera versión de la voz");
    fireEvent.click(screen.getByRole("button", { name: "Restaurar" }));
    await waitFor(() =>
      expect(llamadas.some((l) => l.metodo === "POST" && l.path.endsWith("/solicitar"))).toBe(true),
    );
    expect(llamadas.some((l) => l.path.endsWith("/publicar"))).toBe(false);
  });
});
