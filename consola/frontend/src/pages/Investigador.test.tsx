import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import * as React from "react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import type { UsuarioSesion } from "@/types";

import Investigador from "./Investigador";

// Respuesta de `/parrilla-dia` (Plan de hoy): un único posteo jerarquizado.
const PARRILLA = {
  marca: "unotv",
  total_entrada: 2,
  total_posteos: 2,
  total_editorial: 0,
  total_sobrantes: 0,
  total_fuera_foco: 0,
  cuota_posteos: 13,
  cuota_editorial: 6,
  geos_disponibles: [{ id: "MX", nombre: "México" }],
  posteos: [
    {
      tipo: "posteo",
      subtipo: "normal",
      orden: 1,
      score: 0.91,
      titulo: "Sismo en CDMX",
      senal_texto: "Tendencia X",
      razon: "Lo más viral del día.",
      por_que: "Pico de búsquedas.",
      redes: ["x"],
      enlaces: [],
      // Investigador F2b: prioritario (algo fuerte) y aún sin gestionar (nuevo => sin badge de estado).
      // F3: además su señal está acelerando => badge "En aumento".
      estado: "nuevo",
      prioritario: true,
      breaking: true,
    },
    {
      tipo: "posteo",
      subtipo: "normal",
      orden: 2,
      score: 0.7,
      titulo: "Nota ya gestionada",
      senal_texto: "Tendencia Y",
      razon: "Ya en la parrilla.",
      por_que: "Cobertura programada.",
      redes: ["x"],
      enlaces: [],
      // En parrilla y no prioritario => badge "En parrilla", sin "Prioritario".
      // F3: breaking false => sin badge "En aumento".
      estado: "en_parrilla",
      prioritario: false,
      breaking: false,
    },
  ],
  editorial: [],
  sobrantes: [],
};

// Respuesta de `/radar` (Descubrimiento): una tendencia cruda.
const RADAR = {
  marca: "unotv",
  total: 2,
  total_fuera_foco: 0,
  geos_disponibles: [{ id: "MX", nombre: "México" }],
  temas: [
    {
      titulo: "Tendencia viral de prueba",
      curado: false,
      senal_texto: "Sube fuerte",
      redes: ["x"],
      fuentes: ["Google Trends"],
      por_que: "Pico de interés.",
      enlaces: [],
      // Investigador F2b: ya publicado y prioritario => badges "Publicado" + "Prioritario".
      // F3: además su señal está acelerando => badge "En aumento".
      estado: "publicado",
      prioritario: true,
      breaking: true,
    },
    {
      titulo: "Tendencia nueva sin marcar",
      curado: false,
      senal_texto: "Apenas asoma",
      redes: ["x"],
      fuentes: ["Google Trends"],
      por_que: "Empieza a moverse.",
      enlaces: [],
      // Nuevo + no prioritario => ningún badge de estado/prioridad.
      estado: "nuevo",
      prioritario: false,
    },
  ],
  fuentes: [{ id: "trends", nombre: "Google Trends", disponible: true, conteo: 1, motivo: "" }],
  fuentes_pendientes: [],
};

function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/api/parrilla-dia")) {
        return new Response(JSON.stringify(PARRILLA), { status: 200 });
      }
      if (ruta.includes("/api/radar")) {
        return new Response(JSON.stringify(RADAR), { status: 200 });
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

function usuario(): UsuarioSesion {
  return {
    id: "u1",
    usuario: "ana",
    rol: "editor",
    debe_cambiar_password: false,
    marcas: ["unotv"],
  };
}

function sesionValor(u: UsuarioSesion | null): ValorSesion {
  return {
    usuario: u,
    cargando: false,
    iniciarSesion: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
}

function renderConProviders(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <SesionContexto.Provider value={sesionValor(usuario())}>
        <MarcaActivaProvider>
          <MemoryRouter>{ui}</MemoryRouter>
        </MarcaActivaProvider>
      </SesionContexto.Provider>
    </QueryClientProvider>,
  );
}

describe("Investigador", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
    });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("muestra el título y el Plan de hoy por defecto", async () => {
    stubFetch();
    renderConProviders(<Investigador />);

    expect(await screen.findByRole("heading", { name: "El Investigador" })).toBeInTheDocument();
    // El segmento "Plan de hoy" es el activo por defecto: se ve el plan del día.
    expect(await screen.findByText("Sismo en CDMX")).toBeInTheDocument();
  });

  it("cambia a Descubrimiento y renderiza el panel de tendencias", async () => {
    stubFetch();
    renderConProviders(<Investigador />);

    // Espera a que cargue el plan antes de cambiar de segmento.
    await screen.findByText("Sismo en CDMX");

    // Radix Tabs activa con `mousedown` (botón 0), no con `click`.
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Descubrimiento" }), { button: 0 });

    expect(await screen.findByText("Tendencia viral de prueba")).toBeInTheDocument();
  });

  it("pinta los badges de estado y prioridad en el Plan de hoy (F2b)", async () => {
    stubFetch();
    renderConProviders(<Investigador />);

    // El ítem prioritario y nuevo: badge "Prioritario", sin "En parrilla" ni "Publicado".
    await screen.findByText("Sismo en CDMX");
    expect(screen.getByText("Prioritario")).toBeInTheDocument();
    // El segundo ítem está en parrilla y no es prioritario: badge "En parrilla".
    expect(screen.getByText("En parrilla")).toBeInTheDocument();
    // No hay ningún ítem publicado en el Plan: no aparece el badge "Publicado".
    expect(screen.queryByText("Publicado")).not.toBeInTheDocument();
    // Solo un ítem es prioritario (el primero); no hay un segundo badge "Prioritario".
    expect(screen.getAllByText("Prioritario")).toHaveLength(1);
    // F3: el primer ítem trae breaking:true => badge "En aumento"; el segundo (false) no.
    expect(screen.getByText("En aumento")).toBeInTheDocument();
    expect(screen.getAllByText("En aumento")).toHaveLength(1);
  });

  it("pinta los badges de estado y prioridad en Descubrimiento (F2b)", async () => {
    stubFetch();
    renderConProviders(<Investigador />);

    await screen.findByText("Sismo en CDMX");
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Descubrimiento" }), { button: 0 });

    // Tema publicado + prioritario => badges "Publicado" y "Prioritario".
    await screen.findByText("Tendencia viral de prueba");
    expect(screen.getByText("Publicado")).toBeInTheDocument();
    expect(screen.getByText("Prioritario")).toBeInTheDocument();
    // El tema nuevo y no prioritario NO añade badges: solo hay uno de cada.
    expect(screen.getByText("Tendencia nueva sin marcar")).toBeInTheDocument();
    expect(screen.getAllByText("Prioritario")).toHaveLength(1);
    expect(screen.queryByText("En parrilla")).not.toBeInTheDocument();
    // F3: el primer tema trae breaking:true => "En aumento"; el segundo (sin la clave) no.
    expect(screen.getByText("En aumento")).toBeInTheDocument();
    expect(screen.getAllByText("En aumento")).toHaveLength(1);
  });
});
