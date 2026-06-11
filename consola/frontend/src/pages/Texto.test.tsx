/**
 * Biblioteca de Prompts (página Texto, rediseño):
 *   - Vista "La máquina" por defecto: el riel de grupos en orden real, tarjetas de etapa
 *     con su estado de publicación y la pila de capas editoriales de la marca activa.
 *   - Indicadores del header: cambios sin publicar (clic = tabla filtrada) y solicitudes
 *     pendientes (clic = bandeja, solo admin).
 *   - Vista "Todos los documentos" (?vista=todos): tabla plana con estado de publicación.
 *   - Detalle (?doc=…): cabecera de estado con línea de deployment, Publicar (admin),
 *     Probar (prompts) y panel lateral con pestañas (Versiones/Uso/Compilado/Ficha).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import { SesionProvider } from "@/hooks/use-sesion";
import type { DocumentoTexto } from "@/types";

import Texto from "./Texto";

const ADMIN = {
  id: "u0",
  usuario: "admin",
  rol: "admin",
  es_admin: true,
  debe_cambiar_password: false,
  marcas: ["unotv"],
};

const DOC_COPY: DocumentoTexto = {
  id: "prompt/copy",
  titulo: "Prompt de copy",
  descripcion: "Genera el copy por red",
  tipo: "prompt",
  carpeta: "pipelines",
  cuerpo: "Escribe el copy para {{MARCA}}.",
  creado: "2026-05-01T10:00:00",
  actualizado: "2026-06-10T10:00:00",
  clase: "",
  marcas: [],
  salida: "piezas",
  estado: "activo",
  etiquetas: ["copy"],
  pipelines: [],
  rol: "copy",
  prioridad: 0,
  procesos: ["Pipeline de producción (copy)"],
  produccion: { sha: "c0", autor: "ana", nota: "primera", creado: "2026-06-01T09:00:00" },
  sha_actual: "c1",
  sin_publicar: true,
};

const DOC_FUSION: DocumentoTexto = {
  id: "prompt/fusion",
  titulo: "Fusión de historias",
  tipo: "prompt",
  carpeta: "pipelines",
  cuerpo: "Agrupa historias.",
  creado: "2026-05-01T10:00:00",
  actualizado: "2026-06-01T10:00:00",
  clase: "",
  marcas: [],
  estado: "activo",
  produccion: { sha: "a1", autor: "ana", nota: "v1", creado: "2026-05-20T09:00:00" },
  sha_actual: "a1",
  sin_publicar: false,
};

const DOC_VOZ: DocumentoTexto = {
  id: "editorial/voz-unotv",
  titulo: "Voz UnoTV",
  tipo: "editorial",
  carpeta: "editorial",
  cuerpo: "Tono cercano.",
  creado: "2026-05-01T10:00:00",
  actualizado: "2026-06-02T10:00:00",
  clase: "voz",
  marcas: ["unotv"],
  estado: "activo",
  produccion: null,
  sha_actual: null,
  sin_publicar: false,
};

const DOCS = [DOC_COPY, DOC_FUSION, DOC_VOZ];

const MAQUINA = {
  grupos: [
    {
      id: "ingesta",
      titulo: "Ingesta",
      etapas: [
        {
          id: "fusion",
          titulo: "Fusión de historias",
          doc_id: "prompt/fusion",
          produccion: DOC_FUSION.produccion,
          sha_actual: "a1",
          sin_publicar: false,
        },
      ],
    },
    {
      id: "priorizacion",
      titulo: "Priorización",
      etapas: [
        {
          id: "editorial",
          titulo: "Perfil editorial (keywords por marca)",
          doc_id: "prompt/editorial",
          produccion: null,
          sha_actual: "b1",
          sin_publicar: false,
        },
      ],
    },
    {
      id: "produccion",
      titulo: "Producción",
      etapas: [
        {
          id: "copy",
          titulo: "Generación de copy",
          doc_id: "prompt/copy",
          produccion: DOC_COPY.produccion,
          sha_actual: "c1",
          sin_publicar: true,
        },
      ],
    },
    {
      id: "talleres",
      titulo: "Talleres y herramientas",
      etapas: [
        {
          id: "sugerencias",
          titulo: "Sugerencias editoriales",
          doc_id: "prompt/sugerencias",
          produccion: null,
          sha_actual: null,
          sin_publicar: false,
        },
      ],
    },
  ],
  capas: [
    {
      doc_id: "editorial/voz-unotv",
      titulo: "Voz UnoTV",
      clase: "voz",
      orden: 1,
      produccion: null,
      sha_actual: null,
      sin_publicar: false,
    },
  ],
};

const VALIDACION = {
  completa: false,
  faltan: ["tropicalizacion"],
  recomendacion: "Falta la capa de tropicalización MX.",
  pilares: { marca: true, voz: true, plataforma: true, tropicalizacion: false },
};

const SOLICITUDES = [
  {
    id: "s1",
    doc_id: "prompt/copy",
    titulo: "Prompt de copy",
    sha_propuesto: "c1",
    autor: "luis",
    nota: "Mejora el gancho",
    estado: "abierta",
    creado: "2026-06-10T09:00:00",
  },
];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

/** Stub de fetch de todo el dominio texto + sesión + catálogo de marcas. */
function stubFetch() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL, init?: RequestInit) => {
      const path = new URL(String(url), "http://localhost").pathname;
      const metodo = (init?.method ?? "GET").toUpperCase();

      if (path === "/api/auth/me") return json({ usuario: ADMIN });
      if (path === "/api/publicaciones/opciones")
        return json({ marcas: [{ id: "unotv", nombre: "UnoTV" }], redes: [], estados: [] });
      if (path === "/api/texto/maquina") return json(MAQUINA);
      if (path === "/api/texto/validacion") return json(VALIDACION);
      if (path === "/api/texto/solicitudes") return json({ solicitudes: SOLICITUDES });
      if (path === "/api/texto/variables")
        return json({
          variables: [
            { nombre: "MARCA", descripcion: "Marca activa", ejemplo: "UnoTV", origen: "marca" },
          ],
        });
      if (path === "/api/texto/marcas")
        return json({ marcas: [{ id: "unotv", nombre: "UnoTV" }] });
      if (path === "/api/texto/areas") return json({ areas: [] });
      if (path === "/api/texto/pipelines")
        return json({
          pipelines: [
            {
              id: "copy",
              titulo: "Copy",
              descripcion: "",
              rol: "copy",
              prompt_base_id: "prompt/copy",
            },
          ],
        });
      if (path === "/api/texto" && metodo === "GET")
        return json({ documentos: DOCS, carpetas: ["pipelines", "editorial"] });
      if (path.endsWith("/historial"))
        return json({
          historial: [
            { sha: "c1", sha_corto: "c1", fecha: "2026-06-10T10:00:00", autor: "ana", mensaje: "ajuste" },
            { sha: "c0", sha_corto: "c0", fecha: "2026-06-01T09:00:00", autor: "ana", mensaje: "primera" },
          ],
        });
      if (path.includes("/version/")) {
        const sha = path.split("/version/")[1];
        return json({
          documento: { ...DOC_COPY, cuerpo: sha === "c0" ? "Copy viejo." : "Copy nuevo." },
        });
      }
      // Documento individual (el id lleva barras: /api/texto/prompt/copy).
      const doc = DOCS.find((d) => path === `/api/texto/${d.id}`);
      if (doc && metodo === "GET") return json({ documento: doc });
      if (doc && metodo === "PUT") {
        const body = init?.body ? JSON.parse(String(init.body)) : {};
        return json({ documento: { ...doc, ...body, id: doc.id } });
      }
      return json({ error: `sin stub: ${metodo} ${path}` }, 404);
    }),
  );
}

function montar(ruta = "/") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[ruta]}>
        <SesionProvider>
          <MarcaActivaProvider>
            <Texto />
          </MarcaActivaProvider>
        </SesionProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("Biblioteca de Prompts", () => {
  it("muestra la máquina por defecto: grupos en orden, estado de publicación y capas", async () => {
    stubFetch();
    montar();

    // Espera a que la marca activa quede resuelta (la pila de capas la nombra).
    await screen.findByText(/Ensamblaje editorial · UnoTV/);

    // Los cuatro grupos del riel, en el orden real.
    expect(screen.getByText("Ingesta")).toBeInTheDocument();
    expect(screen.getByText("Priorización")).toBeInTheDocument();
    expect(screen.getByText("Producción")).toBeInTheDocument();
    expect(screen.getByText("Talleres y herramientas")).toBeInTheDocument();

    // Tarjeta de etapa con el nombre del prompt y su estado de publicación.
    expect(screen.getByText("Generación de copy")).toBeInTheDocument();
    expect(screen.getAllByText("v. de producción").length).toBeGreaterThan(0);
    expect(screen.getAllByText("sin publicar").length).toBeGreaterThan(0);

    // Pila de capas editoriales de la marca activa + pilar que falta.
    expect(screen.getByText("Voz UnoTV")).toBeInTheDocument();
    expect(await screen.findByText(/Tropicalización — vacía/)).toBeInTheDocument();

    // Indicadores del header: cambios sin publicar y solicitudes (admin).
    expect(await screen.findByText(/1 cambio sin publicar/)).toBeInTheDocument();
    expect(await screen.findByText(/1 solicitud/)).toBeInTheDocument();
  });

  it("el indicador de cambios lleva a la tabla filtrada por «sin publicar»", async () => {
    stubFetch();
    montar();

    await screen.findByText(/Ensamblaje editorial · UnoTV/);
    fireEvent.click(screen.getByText(/1 cambio sin publicar/));
    // Tabla plana con SOLO el documento con cambios, y el chip del filtro activo.
    expect(await screen.findByText(/solo sin publicar/)).toBeInTheDocument();
    expect(await screen.findByText("Prompt de copy")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Voz UnoTV")).not.toBeInTheDocument());
  });

  it("la vista de todos los documentos lista la tabla completa con su publicación", async () => {
    stubFetch();
    montar("/?vista=todos");

    // Espera a que la marca activa quede resuelta (el selector muestra su nombre)
    // y la tabla cargue su listado definitivo.
    await screen.findByText("UnoTV");
    await waitFor(() => expect(screen.getByText("Prompt de copy")).toBeInTheDocument());
    expect(screen.getByText("Fusión de historias")).toBeInTheDocument();
    expect(screen.getByText("Voz UnoTV")).toBeInTheDocument();
    // Estado de publicación en la tabla: punteros de producción y aviso sin publicar.
    expect(screen.getAllByText("● prod").length).toBe(2);
    expect(screen.getByText("sin publicar")).toBeInTheDocument();
    // La papelera es accesible desde aquí.
    expect(screen.getByRole("button", { name: /Papelera/ })).toBeInTheDocument();
  });

  it("abre el detalle desde el riel: cabecera de estado, acciones y panel de pestañas", async () => {
    stubFetch();
    montar();

    // Espera a que la marca quede resuelta (el riel deja de re-cargarse) antes de clicar.
    await screen.findByText(/Ensamblaje editorial · UnoTV/);
    fireEvent.click(screen.getByTitle("Generación de copy — abrir el prompt"));

    // Cabecera: título editable, línea de deployment, badge sin publicar y acciones.
    expect(await screen.findByDisplayValue("Prompt de copy")).toBeInTheDocument();
    expect(screen.getByText(/v\. producción desde/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publicar/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Probar/ })).toBeInTheDocument();
    // Nota informativa de inyección (sustituye al candado).
    expect(screen.getByText(/Inyectado en:/)).toBeInTheDocument();
    // Panel lateral: pestañas Versiones / Uso / Compilado (es prompt base) / Ficha.
    expect(screen.getByRole("tab", { name: "Versiones" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Uso" })).toBeInTheDocument();
    await screen.findByRole("tab", { name: "Compilado" });
    expect(screen.getByRole("tab", { name: "Ficha" })).toBeInTheDocument();
    // El candado desapareció: ya no existe "forzar edición".
    expect(screen.queryByText(/forzar/i)).not.toBeInTheDocument();
  });

  it("abre la bandeja de solicitudes desde el indicador (admin)", async () => {
    stubFetch();
    montar();

    await screen.findByText(/Ensamblaje editorial · UnoTV/);
    fireEvent.click(screen.getByText(/1 solicitud/));
    expect(await screen.findByText("Bandeja de solicitudes")).toBeInTheDocument();
    expect(await screen.findByText("Mejora el gancho")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Aprobar y publicar/ })).toBeInTheDocument();
  });

  it("la búsqueda desde la máquina salta a la tabla y filtra en cliente", async () => {
    stubFetch();
    montar();

    await screen.findByText(/Ensamblaje editorial · UnoTV/);
    fireEvent.change(screen.getByLabelText("Buscar documentos"), {
      target: { value: "voz" },
    });
    expect(await screen.findByText("Voz UnoTV")).toBeInTheDocument();
    expect(screen.queryByText(/Talleres y herramientas/)).not.toBeInTheDocument();
  });
});
