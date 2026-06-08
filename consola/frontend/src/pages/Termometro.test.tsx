import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import type { UsuarioSesion } from "@/types";

import Termometro from "./Termometro";

/** Sesión mínima para montar el provider de marca activa (editor sin marca → "Todas"). */
function sesionValor(): ValorSesion {
  const usuario: UsuarioSesion = {
    id: "u1",
    usuario: "ana",
    rol: "admin",
    debe_cambiar_password: false,
    marcas: [],
  };
  return {
    usuario,
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

const PAYLOAD_BASE = {
  config: { numero: 8, regiones: "", hora: "07:00", marca: "" },
  prompt_disponible: true,
  marcas: [
    { id: "unotv", nombre: "UnoTV" },
    { id: "claro-sports", nombre: "Claro Sports" },
  ],
  regiones_sugeridas: ["EEUU", "Europa", "Asia"],
  ultimo: null,
};

const OPCIONES_REDES = {
  redes: [
    { id: "x", nombre: "X" },
    { id: "instagram", nombre: "Instagram" },
    { id: "facebook", nombre: "Facebook" },
  ],
};

function stubFetch(payload: object) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/termometro")) {
        return new Response(JSON.stringify(payload), { status: 200 });
      }
      if (ruta.includes("/api/publicaciones/opciones")) {
        return new Response(JSON.stringify(OPCIONES_REDES), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor()}>
        <MarcaActivaProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("Termometro", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("carga la config y muestra el encabezado y el formulario", async () => {
    stubFetch(PAYLOAD_BASE);
    renderConProviders(<Termometro />);

    expect(await screen.findByRole("heading", { name: "Termómetro mundial" })).toBeInTheDocument();
    // El formulario de generación aparece tras cargar la config.
    expect(await screen.findByLabelText(/noticias internacionales del día/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /generar termómetro/i })).toBeInTheDocument();
  });

  it("deshabilita Generar sin noticias y lo habilita al escribirlas", async () => {
    stubFetch(PAYLOAD_BASE);
    renderConProviders(<Termometro />);

    const boton = await screen.findByRole("button", { name: /generar termómetro/i });
    expect(boton).toBeDisabled();

    const noticias = screen.getByLabelText(/noticias internacionales del día/i);
    fireEvent.change(noticias, { target: { value: "China: algo grande.\nEuropa: otra cosa." } });
    expect(boton).toBeEnabled();
  });

  it("repinta el último termómetro guardado (resultado persistente)", async () => {
    stubFetch({
      ...PAYLOAD_BASE,
      ultimo: {
        historial_id: "h-123",
        documento: "Galeria internacional del dia de ayer",
        titulo: "Termómetro mundial · 2026-05-31",
        fecha: "2026-05-31",
        marca: "unotv",
      },
    });
    renderConProviders(<Termometro />);

    // El documento del último termómetro aparece sin haber generado nada en esta sesión.
    expect(await screen.findByText(/galeria internacional del dia de ayer/i)).toBeInTheDocument();
    // Y se muestra dentro del nuevo visor visual del termómetro (no el Card genérico).
    expect(screen.getByTestId("termometro-preview")).toBeInTheDocument();
  });

  it("renderiza la galería como portada + slides en miniatura", async () => {
    const documento = [
      "REVISAR ANTES DE PUBLICAR · pulso internacional cargado.",
      "",
      "Termómetro mundial · 2026-05-31",
      "El mundo amanece con tres frentes calientes.",
      "",
      "2/8 — EEUU (serio): La Fed sube tasas",
      "Wall Street reacciona a la baja.",
      "",
      "3/8 — Europa (viral/redes): Viral en Madrid",
      "Un video se hace tendencia.",
      "",
      "## Fuentes",
      "- [Reuters](https://reuters.com)",
      "",
      "## Auto-verificación",
      "Frescura cruzada con 2 fuentes.",
      "",
      '```json',
      '{"piezas": [{"red": "x", "texto": "hilo", "copy_in": ""}]}',
      "```",
    ].join("\n");
    stubFetch({
      ...PAYLOAD_BASE,
      ultimo: {
        historial_id: "h-456",
        documento,
        titulo: "Termómetro mundial · 2026-05-31",
        fecha: "2026-05-31",
        marca: "unotv",
      },
    });
    renderConProviders(<Termometro />);

    // Portada + los dos slides como tarjetas (texto por subcadena dentro del título).
    expect(
      await screen.findByText((t) => /term[óo]metro mundial · 2026-05-31/i.test(t)),
    ).toBeInTheDocument();
    expect(screen.getByText((t) => /la fed sube tasas/i.test(t))).toBeInTheDocument();
    expect(screen.getByText((t) => /viral en madrid/i.test(t))).toBeInTheDocument();
    // Veredicto destacado.
    expect(screen.getByText((t) => /revisar antes de publicar/i.test(t))).toBeInTheDocument();
    // El bloque JSON de piezas NO se muestra como texto.
    expect(screen.queryByText(/"piezas"/)).not.toBeInTheDocument();
    // Hay selector de redes (chips multi-red) para guardar.
    const chips = await screen.findAllByRole("checkbox");
    expect(chips.length).toBe(OPCIONES_REDES.redes.length);
    expect(chips.map((c) => c.getAttribute("aria-label"))).toContain("X");
  });

  it("avisa cuando falta el prompt base en la Texto", async () => {
    stubFetch({ ...PAYLOAD_BASE, prompt_disponible: false });
    renderConProviders(<Termometro />);

    expect(await screen.findByText(/falta el prompt base del termómetro/i)).toBeInTheDocument();
    // Sin el prompt base, no se puede generar aunque haya noticias.
    const noticias = await screen.findByLabelText(/noticias internacionales del día/i);
    fireEvent.change(noticias, { target: { value: "algo" } });
    expect(screen.getByRole("button", { name: /generar termómetro/i })).toBeDisabled();
  });
});
