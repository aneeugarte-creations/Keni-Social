/**
 * Biblioteca de Prompts (página Texto, rediseño TRES MÁQUINAS + Estrategia de marca):
 *   - Pestañas principales (?vista=): Investigación (default) | Producción | Importación |
 *     Estrategia de marca | Documentos.
 *   - Cada pestaña de máquina pinta SU riel de `GET /api/texto/maquina` ({maquinas}),
 *     discriminando etapas `prompt` (tarjetas clicables) de `mecanica` (nodos fantasma),
 *     con el evergreen (seccion "taller") separado como anexo «Taller».
 *   - Estrategia de marca monta `EstrategiaMarca` con la marca activa global.
 *   - Documentos: tabla plana con filtros + papelera; ahí vive el filtro "sin publicar".
 *   - Header global: búsqueda (salta a Documentos), badge de cambios sin publicar y
 *     solicitudes pendientes (admins).
 *   - Detalle (?doc=…): se conserva; «Uso» describe máquina → etapa, y volver regresa
 *     a la pestaña de origen.
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

/** Las TRES máquinas del contrato nuevo: etapas discriminadas por `tipo`. */
const MAQUINA = {
  maquinas: [
    {
      id: "investigacion",
      titulo: "Investigación",
      subtitulo: "El motor de noticias",
      etapas: [
        { tipo: "mecanica", id: "ingesta", titulo: "Ingesta" },
        { tipo: "mecanica", id: "clustering", titulo: "Clustering y merge léxico" },
        {
          tipo: "prompt",
          id: "fusion",
          titulo: "Fusión",
          doc_id: "prompt/fusion",
          produccion: DOC_FUSION.produccion,
          sha_actual: "a1",
          sin_publicar: false,
        },
        { tipo: "mecanica", id: "admision", titulo: "Admisión" },
      ],
    },
    {
      id: "produccion",
      titulo: "Producción",
      subtitulo: "La máquina de contenido",
      etapas: [
        {
          tipo: "prompt",
          id: "copy",
          titulo: "Copy",
          doc_id: "prompt/copy",
          produccion: DOC_COPY.produccion,
          sha_actual: "c1",
          sin_publicar: true,
        },
        { tipo: "mecanica", id: "aprobacion", titulo: "Aprobación" },
        { tipo: "mecanica", id: "publicacion", titulo: "Publicación" },
        {
          tipo: "prompt",
          id: "evergreen",
          titulo: "Taller evergreen",
          doc_id: "prompt/evergreen",
          produccion: null,
          sha_actual: null,
          sin_publicar: false,
          seccion: "taller",
        },
      ],
    },
    {
      id: "importacion",
      titulo: "Herramientas de importación",
      subtitulo: "Insumos del equipo",
      etapas: [
        {
          tipo: "prompt",
          id: "insumos-portal",
          titulo: "Insumos · Portal/SMS",
          doc_id: "prompt/insumos/portal",
          produccion: null,
          sha_actual: null,
          sin_publicar: false,
        },
      ],
    },
  ],
};

/** `GET /api/texto/estrategia?marca=unotv` (lo consume EstrategiaMarca). */
const ESTRATEGIA = {
  marca: "unotv",
  completitud: {
    completa: false,
    faltan: ["tropicalizacion"],
    recomendacion: "Falta la capa de tropicalización MX.",
  },
  pilares: [
    {
      clase: "voz",
      titulo: "Voz UnoTV",
      doc_id: "editorial/voz-unotv",
      vacio: false,
      global: false,
      produccion: null,
      sha_actual: null,
      sin_publicar: false,
      actualizado: "2026-06-02T10:00:00",
      extracto: "Tono cercano.",
    },
  ],
  extras: [],
  orden_inyeccion: ["editorial/voz-unotv"],
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
      if (path === "/api/texto/estrategia") return json(ESTRATEGIA);
      if (path === "/api/texto/validacion")
        return json({
          completa: false,
          faltan: ["tropicalizacion"],
          recomendacion: "Falta la capa de tropicalización MX.",
          pilares: { marca: true, voz: true, plataforma: true, tropicalizacion: false },
        });
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

describe("Biblioteca de Prompts (tres máquinas + estrategia)", () => {
  it("muestra Investigación por defecto: cabecera, etapas prompt y nodos mecánicos", async () => {
    stubFetch();
    montar();

    // Cabecera de la máquina: título + lema del ADR 0011.
    expect(await screen.findByText("El motor de noticias")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Investigación" })).toBeInTheDocument();

    // Las cinco pestañas principales.
    expect(screen.getByRole("tab", { name: "Investigación" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Producción" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Importación" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Estrategia de marca" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Documentos" })).toBeInTheDocument();

    // Etapa con prompt: tarjeta clicable con el nombre del doc y su publicación.
    const tarjeta = screen.getByTitle("Fusión — abrir el prompt");
    expect(tarjeta.tagName).toBe("BUTTON");
    // El nombre del doc sale del listado (carga aparte): espera a que aparezca.
    expect(await screen.findByText("Fusión de historias")).toBeInTheDocument();
    expect(screen.getAllByText("producción").length).toBeGreaterThan(0);

    // Etapa mecánica: nodo fantasma NO clicable, con tooltip explicativo.
    const mecanica = screen.getByText("Ingesta");
    expect(mecanica.closest("button")).toBeNull();
    expect(screen.getAllByTitle("Etapa automática sin prompt").length).toBe(3);

    // Enlace cruzado a la página del proceso (ADR 0011 F2): el proceso en vivo de
    // Investigación vive ahora en su cockpit (`/maquina/investigacion`).
    expect(
      screen.getByRole("link", { name: /Ver el proceso en vivo/ }).getAttribute("href"),
    ).toBe("/maquina/investigacion");

    // Salud agregada: en Investigación no hay cambios pendientes.
    expect(screen.getByText("todo publicado")).toBeInTheDocument();

    // Indicadores del header global: cambios sin publicar y solicitudes (admin).
    expect(await screen.findByText(/1 cambio sin publicar/)).toBeInTheDocument();
    expect(await screen.findByText(/1 solicitud/)).toBeInTheDocument();
  });

  it("Producción: salud agregada, anexo «Taller» y enlace a Estrategia de marca", async () => {
    stubFetch();
    montar("/?vista=produccion");

    expect(await screen.findByText("La máquina de contenido")).toBeInTheDocument();
    // Salud agregada: el copy tiene cambios sin publicar.
    expect(screen.getByText(/1 etapa sin publicar/)).toBeInTheDocument();

    // Enlace cruzado a la página del proceso: el feed de Producción se plegó en la página
    // Agentes (sección «Actividad»), así que el proceso «en vivo» de Producción es /maquina/agentes.
    expect(
      screen.getByRole("link", { name: /Ver el proceso en vivo/ }).getAttribute("href"),
    ).toBe("/maquina/agentes");

    // El evergreen (seccion "taller") vive separado del riel principal.
    const taller = screen.getByRole("region", { name: "Taller" });
    expect(taller).toContainElement(screen.getByText("Taller evergreen"));

    // Bajo la etapa de copy, el enlace discreto salta a la pestaña Estrategia de marca.
    fireEvent.click(
      screen.getByText(/Las capas editoriales de la marca viven en Estrategia de marca/),
    );
    expect(await screen.findByText("Cómo se ensambla para la IA")).toBeInTheDocument();
  });

  it("Importación pinta su máquina (?vista=importacion)", async () => {
    stubFetch();
    montar("/?vista=importacion");

    expect(await screen.findByText("Insumos del equipo")).toBeInTheDocument();
    expect(screen.getByTitle("Insumos · Portal/SMS — abrir el prompt")).toBeInTheDocument();
  });

  it("Estrategia de marca monta el espacio de la marca activa y abre documentos", async () => {
    stubFetch();
    montar("/?vista=estrategia");

    // Los pilares (tarjetas grandes) + el ensamblaje real de la marca.
    expect(await screen.findByText("Identidad de marca")).toBeInTheDocument();
    expect(screen.getByText("Cómo se ensambla para la IA")).toBeInTheDocument();
    expect(screen.getByTestId("pilar-voz")).toBeInTheDocument();

    // Abrir el documento de un pilar lleva a la vista detalle de la página.
    fireEvent.click(screen.getByRole("button", { name: "Abrir" }));
    expect(await screen.findByDisplayValue("Voz UnoTV")).toBeInTheDocument();
  });

  it("el indicador de cambios lleva a Documentos filtrado por «sin publicar»", async () => {
    stubFetch();
    montar();

    await screen.findByText("El motor de noticias");
    fireEvent.click(await screen.findByText(/1 cambio sin publicar/));
    // Tabla plana con SOLO el documento con cambios, y el chip del filtro activo.
    expect(await screen.findByText(/solo sin publicar/)).toBeInTheDocument();
    expect(await screen.findByText("Prompt de copy")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByText("Voz UnoTV")).not.toBeInTheDocument());
  });

  it("Documentos lista la tabla completa con su publicación y la papelera", async () => {
    stubFetch();
    montar("/?vista=documentos");

    await waitFor(() => expect(screen.getByText("Prompt de copy")).toBeInTheDocument());
    expect(screen.getByText("Fusión de historias")).toBeInTheDocument();
    expect(screen.getByText("Voz UnoTV")).toBeInTheDocument();
    // Estado de publicación en la tabla: punteros de producción y aviso sin publicar.
    expect(screen.getAllByText("● prod").length).toBe(2);
    expect(screen.getByText("sin publicar")).toBeInTheDocument();
    // La papelera es accesible desde aquí.
    expect(screen.getByRole("button", { name: /Papelera/ })).toBeInTheDocument();
  });

  it("abre el detalle desde el riel, «Uso» sitúa máquina → etapa y vuelve a la pestaña de origen", async () => {
    stubFetch();
    montar("/?vista=produccion");

    await screen.findByText("La máquina de contenido");
    fireEvent.click(screen.getByTitle("Copy — abrir el prompt"));

    // Cabecera: título editable, línea de deployment, badge sin publicar y acciones.
    expect(await screen.findByDisplayValue("Prompt de copy")).toBeInTheDocument();
    expect(screen.getByText(/v\. producción desde/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Publicar/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Probar/ })).toBeInTheDocument();

    // Pestaña «Uso»: la posición nueva, máquina → etapa (del endpoint nuevo).
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Uso" }), { button: 0 });
    expect(await screen.findByText("Producción → Copy")).toBeInTheDocument();

    // Volver regresa a la pestaña de origen (Producción), no a la vista por defecto.
    fireEvent.click(screen.getByRole("button", { name: "Volver a la biblioteca" }));
    expect(await screen.findByText("La máquina de contenido")).toBeInTheDocument();
  });

  it("abre la bandeja de solicitudes desde el indicador (admin)", async () => {
    stubFetch();
    montar();

    await screen.findByText("El motor de noticias");
    fireEvent.click(await screen.findByText(/1 solicitud/));
    expect(await screen.findByText("Bandeja de solicitudes")).toBeInTheDocument();
    expect(await screen.findByText("Mejora el gancho")).toBeInTheDocument();
    // Las acciones (Aprobar/Rechazar) viven en menú contextual (item-first, kebab="nunca").
    const host = screen.getByText("Mejora el gancho").closest("[role='button']")!;
    fireEvent.contextMenu(host);
    expect(screen.getByRole("menuitem", { name: /Aprobar y publicar/ })).toBeInTheDocument();
  });

  it("la búsqueda global salta a Documentos y filtra en cliente", async () => {
    stubFetch();
    montar();

    await screen.findByText("El motor de noticias");
    fireEvent.change(screen.getByLabelText("Buscar documentos"), {
      target: { value: "voz" },
    });
    expect(await screen.findByText("Voz UnoTV")).toBeInTheDocument();
    expect(screen.queryByText("El motor de noticias")).not.toBeInTheDocument();
  });
});
