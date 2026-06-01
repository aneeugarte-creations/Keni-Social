import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PiezasRota from "./PiezasRota";

const PIEZAS = [
  {
    id: "p1",
    evento_id: "",
    programa: "MUNDIAL",
    red_social: "IG, TK (REEL)",
    tipo_pieza: "REEL",
    contenido_sugerido: "Resumen del partido",
    dia: "2026-06-01",
    hora_post: "16:00",
    estado: "pendiente",
    material_entregado: false,
    contenido_entregado: false,
    publicado: false,
    enlace: "",
    responsable_id: "u1",
    responsable_nombre: "Diana Ramos",
    notas: "",
    salida: "REDES",
    comentarios: "",
    fecha_entrega_material: "",
    always_on: false,
  },
];

const EQUIPO = { equipo: [{ id: "u1", nombre: "Diana Ramos" }] };

interface Captura {
  url: string;
  metodo: string;
  body: unknown;
}

/** Stub de fetch: GET piezas/equipo; captura POST/PATCH/DELETE. */
function stubFetch(capturas: Captura[] = []) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const ruta = String(url);
      const metodo = (init?.method ?? "GET").toUpperCase();
      const body = init?.body ? JSON.parse(String(init.body)) : undefined;
      if (metodo !== "GET") capturas.push({ url: ruta, metodo, body });

      if (ruta.includes("/api/rota/equipo")) {
        return new Response(JSON.stringify(EQUIPO), { status: 200 });
      }
      if (ruta.includes("/api/rota/piezas") && metodo === "POST") {
        return new Response(JSON.stringify({ pieza: { ...PIEZAS[0], id: "p2" } }), { status: 200 });
      }
      if (ruta.includes("/api/rota/piezas")) {
        return new Response(JSON.stringify({ piezas: PIEZAS }), { status: 200 });
      }
      return new Response(JSON.stringify({}), { status: 200 });
    }),
  );
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PiezasRota · CRUD de piezas de la parrilla", () => {
  beforeEach(() => vi.restoreAllMocks());
  afterEach(() => vi.unstubAllGlobals());

  it("lista las piezas existentes con su estado", async () => {
    stubFetch();
    renderConProviders(<PiezasRota />);

    expect(await screen.findByText("MUNDIAL")).toBeInTheDocument();
    expect(screen.getByText("Pendiente")).toBeInTheDocument();
    expect(screen.getByText("Diana Ramos")).toBeInTheDocument();
  });

  it("crea una pieza nueva vía POST /api/rota/piezas", async () => {
    const capturas: Captura[] = [];
    stubFetch(capturas);
    renderConProviders(<PiezasRota />);

    await screen.findByText("MUNDIAL");
    // Abre el diálogo de alta.
    fireEvent.click(screen.getByRole("button", { name: /nueva pieza/i }));

    const programa = await screen.findByLabelText(/programa/i);
    fireEvent.change(programa, { target: { value: "Paty Cantú" } });

    fireEvent.click(screen.getByRole("button", { name: /crear pieza/i }));

    await waitFor(() => {
      const post = capturas.find(
        (c) => c.url.includes("/api/rota/piezas") && c.metodo === "POST",
      );
      expect(post).toBeTruthy();
      expect((post!.body as { programa: string }).programa).toBe("Paty Cantú");
    });
  });
});
