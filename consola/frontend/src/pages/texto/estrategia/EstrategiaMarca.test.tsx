/**
 * "Estrategia de marca" (componente autónomo del rediseño de la Biblioteca):
 *   - Cabecera de salud: anillo X/4 + recomendación (o estado positivo si está completa).
 *   - 5 pilares como tarjetas en orden fijo, con estados vacío / sin publicar / publicada
 *     y el badge "global".
 *   - Franja "Cómo se ensambla para la IA": chips numerados clicables (onAbrirDoc).
 *   - CTA "Definir ahora" en pilar sin documento: POST /api/texto con la convención
 *     editorial (carpeta rrss/<marca>, clase, marcas) y abre el doc creado.
 *   - Fallback: si `GET /api/texto/estrategia` no existe (404), se construye el mismo
 *     estado desde `GET /api/texto` + `/api/texto/validacion`.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EstrategiaMarca } from "./EstrategiaMarca";
import type { RespuestaEstrategia } from "./tipos";

const PROD = { sha: "a1", autor: "ana", nota: "v1", creado: "2026-06-01T09:00:00" };

const ESTRATEGIA: RespuestaEstrategia = {
  marca: "unotv",
  completitud: {
    completa: false,
    faltan: ["tropicalizacion"],
    recomendacion: "Define la tropicalización MX para completar la estrategia.",
  },
  pilares: [
    {
      clase: "marca",
      titulo: "Identidad · UnoTV",
      doc_id: "editorial/rrss/unotv/marca",
      vacio: false,
      global: false,
      produccion: PROD,
      sha_actual: "a1",
      sin_publicar: false,
      actualizado: "2026-06-01T09:00:00",
      extracto: "UnoTV informa con rigor y sin opinar.",
    },
    {
      clase: "voz",
      titulo: "Voz y tono · UnoTV",
      doc_id: "editorial/rrss/unotv/voz",
      vacio: false,
      global: false,
      produccion: PROD,
      sha_actual: "b2",
      sin_publicar: true,
      actualizado: "2026-06-10T10:00:00",
      cuerpo: "---\ntipo: editorial\n---\n\nVoz informativa, **directa** y verificada.",
    },
    {
      clase: "tropicalizacion",
      titulo: "",
      doc_id: null,
      vacio: true,
      global: false,
      produccion: null,
      sha_actual: null,
      sin_publicar: false,
      actualizado: "",
    },
    {
      clase: "plataforma",
      titulo: "Plataformas (global)",
      doc_id: "editorial/rrss/global/plataformas",
      vacio: false,
      global: true,
      produccion: null,
      sha_actual: "c1",
      sin_publicar: false,
      actualizado: "2026-06-05T10:00:00",
      extracto: "Formato por red: X, Facebook, Instagram, TikTok.",
    },
    {
      clase: "reglas",
      titulo: "Reglas legales (global)",
      doc_id: "editorial/rrss/global/reglas-legales",
      vacio: false,
      global: true,
      produccion: PROD,
      sha_actual: "d1",
      sin_publicar: false,
      actualizado: "2026-06-02T10:00:00",
      extracto: "Nada de datos personales ni menores identificables.",
    },
  ],
  extras: [
    {
      clase: "",
      titulo: "Patrones medidos · UnoTV",
      doc_id: "editorial/rrss/unotv/patrones",
      vacio: false,
      global: false,
      produccion: null,
      sha_actual: "e1",
      sin_publicar: true,
      actualizado: "2026-06-10T06:00:00",
      extracto: "Bandas de rendimiento medidas en Metricool.",
    },
  ],
  orden_inyeccion: [
    "editorial/rrss/unotv/marca",
    "editorial/rrss/unotv/voz",
    "editorial/rrss/global/plataformas",
    "editorial/rrss/global/reglas-legales",
    "editorial/rrss/unotv/patrones",
  ],
};

const DOC_CREADO = {
  id: "editorial/rrss/unotv/tropicalizacion-mx-unotv",
  titulo: "Tropicalización MX · UnoTV",
  tipo: "editorial",
  carpeta: "rrss/unotv",
  cuerpo: "",
  creado: "2026-06-11T10:00:00",
  actualizado: "2026-06-11T10:00:00",
  clase: "tropicalizacion",
  marcas: ["unotv"],
  produccion: null,
  sha_actual: null,
  sin_publicar: false,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

/**
 * Stub de fetch. `opciones.estrategia` permite forzar el 404 (fallback) o una respuesta
 * alternativa; `creados` acumula los cuerpos de los POST a /api/texto.
 */
function stubFetch(opciones: { estrategia?: RespuestaEstrategia | null } = {}) {
  const creados: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const path = new URL(String(url), "http://localhost").pathname;
      const metodo = (init?.method ?? "GET").toUpperCase();

      if (path === "/api/texto/estrategia") {
        const cuerpo = opciones.estrategia === undefined ? ESTRATEGIA : opciones.estrategia;
        return cuerpo ? json(cuerpo) : json({ error: "Esa ruta no existe." }, 404);
      }
      if (path === "/api/texto/marcas")
        return json({ marcas: [{ id: "unotv", nombre: "UnoTV" }] });
      if (path === "/api/texto/validacion")
        return json({
          completa: false,
          faltan: ["tropicalizacion"],
          recomendacion: "Falta la capa de tropicalización MX.",
          pilares: { marca: true, voz: true, plataforma: true, tropicalizacion: false },
        });
      if (path === "/api/texto" && metodo === "GET")
        return json({
          documentos: [
            {
              id: "editorial/rrss/unotv/voz",
              titulo: "Voz UnoTV",
              tipo: "editorial",
              carpeta: "rrss/unotv",
              cuerpo: "Tono cercano y directo.",
              creado: "2026-05-01T10:00:00",
              actualizado: "2026-06-02T10:00:00",
              clase: "voz",
              marcas: ["unotv"],
              prioridad: 2,
              produccion: null,
              sha_actual: null,
              sin_publicar: false,
            },
            {
              id: "editorial/rrss/unotv/marca",
              titulo: "Identidad UnoTV",
              tipo: "editorial",
              carpeta: "rrss/unotv",
              cuerpo: "UnoTV informa con rigor.",
              creado: "2026-05-01T10:00:00",
              actualizado: "2026-06-01T10:00:00",
              clase: "marca",
              marcas: ["unotv"],
              prioridad: 1,
              produccion: PROD,
              sha_actual: "a1",
              sin_publicar: false,
            },
          ],
          carpetas: ["editorial/rrss"],
        });
      if (path === "/api/texto" && metodo === "POST") {
        const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
        creados.push(body);
        return json({ documento: DOC_CREADO });
      }
      return json({ error: `sin stub: ${metodo} ${path}` }, 404);
    }),
  );
  return creados;
}

function montar(props: { marca?: string; onAbrirDoc?: (id: string) => void } = {}) {
  const onAbrirDoc = props.onAbrirDoc ?? vi.fn();
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <EstrategiaMarca marca={props.marca ?? "unotv"} onAbrirDoc={onAbrirDoc} />
    </QueryClientProvider>,
  );
  return onAbrirDoc;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("EstrategiaMarca", () => {
  it("pinta la cabecera de salud y los 5 pilares en orden fijo con sus estados", async () => {
    stubFetch();
    montar();

    // Cabecera: nombre humano de la marca, anillo 3/4 y recomendación.
    expect(await screen.findByText("UnoTV")).toBeInTheDocument();
    expect(screen.getByText("3/4")).toBeInTheDocument();
    expect(
      screen.getByText("Define la tropicalización MX para completar la estrategia."),
    ).toBeInTheDocument();

    // Los 5 pilares, en el orden fijo del contrato.
    const tarjetas = document.querySelectorAll('[data-testid^="pilar-"]');
    expect([...tarjetas].map((t) => t.getAttribute("data-testid"))).toEqual([
      "pilar-marca",
      "pilar-voz",
      "pilar-tropicalizacion",
      "pilar-plataforma",
      "pilar-reglas",
    ]);

    // Estados: publicada / cambios sin publicar / vacía + CTA / global.
    const marca = within(screen.getByTestId("pilar-marca"));
    expect(marca.getByText("publicada")).toBeInTheDocument();
    expect(marca.getByText("UnoTV informa con rigor y sin opinar.")).toBeInTheDocument();

    const voz = within(screen.getByTestId("pilar-voz"));
    expect(voz.getByText("cambios sin publicar")).toBeInTheDocument();
    // Extracto derivado del cuerpo markdown (sin frontmatter ni énfasis).
    expect(voz.getByText("Voz informativa, directa y verificada.")).toBeInTheDocument();

    const tropi = within(screen.getByTestId("pilar-tropicalizacion"));
    expect(tropi.getByText("vacía")).toBeInTheDocument();
    expect(tropi.getByRole("button", { name: /Definir ahora/ })).toBeInTheDocument();

    expect(screen.getAllByText("global")).toHaveLength(2);

    // Material de apoyo (extras): el patrón aparece como tarjeta compacta.
    const apoyo = within(screen.getByRole("region", { name: "Material de apoyo" }));
    expect(apoyo.getByText("Patrones medidos · UnoTV")).toBeInTheDocument();
  });

  it("muestra el estado positivo sobrio cuando la estrategia está completa", async () => {
    stubFetch({
      estrategia: {
        ...ESTRATEGIA,
        completitud: { completa: true, faltan: [], recomendacion: "" },
      },
    });
    montar();

    expect(await screen.findByText("4/4")).toBeInTheDocument();
  });

  it("enseña el orden real de inyección como chips numerados clicables", async () => {
    stubFetch();
    const onAbrirDoc = montar();

    const franja = within(
      await screen.findByRole("region", { name: "Cómo se ensambla para la IA" }),
    );
    const chips = franja.getAllByRole("button");
    expect(chips).toHaveLength(5);
    expect(chips[0]).toHaveTextContent("1");
    expect(chips[0]).toHaveTextContent("Identidad de marca");
    expect(chips[1]).toHaveTextContent("2");
    expect(chips[1]).toHaveTextContent("Voz");
    expect(chips[4]).toHaveTextContent("Patrones medidos · UnoTV");

    fireEvent.click(chips[1]);
    expect(onAbrirDoc).toHaveBeenCalledWith("editorial/rrss/unotv/voz");
  });

  it("«Abrir» delega en onAbrirDoc con el doc_id del pilar", async () => {
    stubFetch();
    const onAbrirDoc = montar();

    const marca = within(await screen.findByTestId("pilar-marca"));
    fireEvent.click(marca.getByRole("button", { name: "Abrir" }));
    expect(onAbrirDoc).toHaveBeenCalledWith("editorial/rrss/unotv/marca");
  });

  it("«Definir ahora» crea el documento con la convención editorial y lo abre", async () => {
    const creados = stubFetch();
    const onAbrirDoc = montar();

    const tropi = within(await screen.findByTestId("pilar-tropicalizacion"));
    fireEvent.click(tropi.getByRole("button", { name: /Definir ahora/ }));

    await waitFor(() => expect(onAbrirDoc).toHaveBeenCalledWith(DOC_CREADO.id));
    expect(creados).toHaveLength(1);
    expect(creados[0]).toMatchObject({
      titulo: "Tropicalización MX · UnoTV",
      tipo: "editorial",
      carpeta: "rrss/unotv",
      clase: "tropicalizacion",
      marcas: ["unotv"],
    });
  });

  it("degrada al fallback (/api/texto + /validacion) si el endpoint nuevo no existe", async () => {
    stubFetch({ estrategia: null });
    montar();

    // Pilares montados desde el listado clásico + diagnóstico (findBy: la validación
    // puede llegar un tick después que el listado).
    expect(await screen.findByTestId("pilar-marca")).toBeInTheDocument();
    expect(await screen.findByText("3/4")).toBeInTheDocument();
    expect(await screen.findByText("Falta la capa de tropicalización MX.")).toBeInTheDocument();

    const marca = within(screen.getByTestId("pilar-marca"));
    expect(marca.getByText("publicada")).toBeInTheDocument();
    const tropi = within(screen.getByTestId("pilar-tropicalizacion"));
    expect(tropi.getByRole("button", { name: /Definir ahora/ })).toBeInTheDocument();

    // El orden de inyección sale de los docs activos (prioridad ascendente).
    const franja = within(screen.getByRole("region", { name: "Cómo se ensambla para la IA" }));
    const chips = franja.getAllByRole("button");
    expect(chips.map((c) => c.textContent)).toEqual(["1Identidad de marca", "2Voz"]);
  });

  it("sin marca, pide elegir una (no revienta)", () => {
    stubFetch();
    montar({ marca: "" });
    expect(screen.getByText("Elige una marca para ver su estrategia.")).toBeInTheDocument();
  });
});
