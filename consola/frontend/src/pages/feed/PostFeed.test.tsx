import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContenedorConfirmacion } from "@/components/comunes/ContenedorConfirmacion";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import type { Publicacion, UsuarioSesion } from "@/types";

import { PostFeed } from "./PostFeed";

// Los avisos de bloqueo del "me gusta" son toasts (no texto fijo): mockeamos sonner para asertarlos.
vi.mock("sonner", () => ({ toast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }) }));

/** Una `Publicacion` completa con valores por defecto (sobreescribibles). */
function pub(over: Partial<Publicacion> = {}): Publicacion {
  return {
    id: "p1",
    contenido_id: "c1",
    titulo: "Tema",
    marca: "piso-15",
    marca_nombre: "Piso 15",
    red: "x",
    red_nombre: "X",
    contenido: "Copy ya redactado por la IA.",
    copy_in: "",
    estado: "pendiente",
    veredicto: "",
    autor_id: "",
    autor_nombre: "",
    enviado_a_revision_en: "",
    revisor_id: "",
    revisor_nombre: "",
    revisado_en: "",
    preparado_en: "",
    id_post_metricool: "",
    tipo_contenido: "ia",
    formato: "foto",
    imagen_fuente: "",
    foto: "",
    falta_copy: false,
    falta_imagen: true,
    falta_revision: true,
    falta_publicar: true,
    falta_video: false,
    video: "",
    fecha_creacion: "",
    fecha_actualizacion: "",
    fecha_programada: "",
    fecha_fuente: "",
    fuente_original: "",
    origen: "pipeline",
    imagen: "",
    imagen_url: "",
    evergreen: false,
    etapa_ia: "generando_arte",
    ...over,
  } as Publicacion;
}

function renderPost(publicacion: Publicacion, usuario: Partial<UsuarioSesion> = {}) {
  const valor: ValorSesion = {
    usuario: { id: "u1", usuario: "revisor", rol: "editor", debe_cambiar_password: false, ...usuario } as UsuarioSesion,
    cargando: false,
    iniciarSesion: vi.fn(),
    verificarConPasskey: vi.fn(),
    verificarConCodigo: vi.fn(),
    cerrarSesion: vi.fn(),
    refrescar: vi.fn(),
  };
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <SesionContexto.Provider value={valor}>
          <PostFeed publicacion={publicacion} />
          {/* La confirmación imperativa (`confirmar`) necesita su contenedor montado. */}
          <ContenedorConfirmacion />
        </SesionContexto.Provider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

/** Stub de fetch para los flujos de aprobación: cadena de UN nivel humano pendiente (el
 *  revisor u1 ≠ autor puede dar OK) y POST /aprobar que devuelve la pieza en `estadoFinal`. */
function stubFetchAprobacion(estadoFinal: Publicacion["estado"]) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string | URL) => {
      const ruta = String(url);
      if (ruta.includes("/aprobar")) {
        return new Response(
          JSON.stringify({ publicacion: pub({ estado: estadoFinal }) }),
          { status: 200 },
        );
      }
      if (ruta.includes("/aprobacion")) {
        return new Response(
          JSON.stringify({
            niveles: [
              {
                id: "n1",
                plataforma_id: "p1",
                contenido_id: "c1",
                nivel: 1,
                etiqueta: "Edición",
                decision: "pendiente",
                decisor_id: "",
                decisor_nombre: "",
                comentario: "",
                creado: "",
                decidido_en: "",
                cargo_requerido: "",
              },
            ],
            estado: "pendiente",
            nivel_actual: "n1",
            aprobados: 0,
            minimo_aprobaciones: 0,
            comentarios_sin_resolver: 0,
          }),
          { status: 200 },
        );
      }
      return new Response("{}", { status: 200 });
    }),
  );
}

describe("PostFeed · firma IA y aviso de bloqueo", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("pieza autogenerada (sin autor) firma como «IA», no «desconocido»", () => {
    renderPost(pub({ autor_nombre: "" }));
    expect(screen.getByText("IA")).toBeInTheDocument();
    expect(screen.queryByText(/desconocido/i)).not.toBeInTheDocument();
  });

  it("enlaza al proceso IA (su run) cuando la pieza nació del pipeline", () => {
    renderPost(pub({ pipeline_id: "c1" }));
    const enlace = screen.getByRole("link", { name: /ver proceso ia/i });
    expect(enlace).toHaveAttribute("href", "/datos/actividad/pipelines/c1");
  });

  it("no ofrece «ver proceso IA» en piezas sin pipeline (manuales/radar/rss)", () => {
    renderPost(pub({ pipeline_id: "" }));
    expect(screen.queryByRole("link", { name: /ver proceso ia/i })).not.toBeInTheDocument();
  });

  it("muestra el icono de formato «Foto» para una pieza con formato foto (3 redes)", () => {
    // El formato va DENTRO del distintivo de cabecera (DistintivoRed): un solo `title`
    // combinado "Red · Formato", iconos pelados sin texto.
    renderPost(pub({ formato: "foto" }));
    expect(screen.getByTitle("X · Foto")).toBeInTheDocument();
    expect(screen.queryByTitle(/· Video$/)).not.toBeInTheDocument();
  });

  it("muestra el icono de formato «Video» para una pieza con formato video (5 redes)", () => {
    renderPost(pub({ formato: "video" }));
    expect(screen.getByTitle("X · Video")).toBeInTheDocument();
    expect(screen.queryByTitle(/· Foto$/)).not.toBeInTheDocument();
  });

  it("pieza posteada por una persona muestra su nombre, no «IA»", () => {
    renderPost(pub({ autor_nombre: "Ana" }));
    expect(screen.getByText(/Ana/)).toBeInTheDocument();
    expect(screen.queryByText(/^IA$/)).not.toBeInTheDocument();
  });

  it("ofrece me gusta y comentar (iconos), NO un botón Editar; la tarjeta abre el editor", () => {
    renderPost(pub());
    // El nombre accesible del like deriva del estado real: aquí está bloqueado (falta material).
    expect(screen.getByRole("button", { name: "Me gusta: no disponible" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comentar" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^editar/i })).not.toBeInTheDocument();
    // La tarjeta completa es clicable (abre el editor).
    expect(screen.getByRole("button", { name: /abrir para editar/i })).toBeInTheDocument();
  });

  it("«Me gusta» cuando NO toca no aprueba: avisa con un toast (falta la imagen) con acción 'Abrir'", () => {
    renderPost(pub({ etapa_ia: "generando_arte" }));
    fireEvent.click(screen.getByRole("button", { name: "Me gusta: no disponible" }));
    // El toast lleva la acción que resuelve el bloqueo (abrir el editor): clave en táctil.
    expect(toast).toHaveBeenCalledWith(
      expect.stringMatching(/Falta la imagen/i),
      expect.objectContaining({ action: expect.anything() }),
    );
  });

  it("pieza VIDEO con falta_video muestra badge 'Falta video' (no 'Falta imagen')", () => {
    renderPost(pub({ formato: "video", falta_video: true, etapa_ia: "generando_arte" }));
    expect(screen.getByText("Falta video")).toBeInTheDocument();
    expect(screen.queryByText("Falta imagen")).not.toBeInTheDocument();
  });

  it("«Me gusta» en pieza VIDEO con falta_video avisa 'Falta el video' con acción 'Abrir'", () => {
    renderPost(pub({ formato: "video", falta_video: true, etapa_ia: "generando_arte" }));
    fireEvent.click(screen.getByRole("button", { name: "Me gusta: no disponible" }));
    expect(toast).toHaveBeenCalledWith(
      expect.stringMatching(/Falta el video/i),
      expect.objectContaining({ action: expect.anything() }),
    );
  });

  it("pieza completa pero fuera de revisión: badge honesto 'En borrador' y like avisa que entra sola", () => {
    renderPost(pub({ etapa_ia: "lista_para_revisar" }));
    // El backend dice "lista para revisar" pero el estado NO es en_revision: el feed normaliza
    // a 'En borrador' (nadie puede darle el OK todavía; un violeta "Para revisar" mentiría).
    expect(screen.getByText("En borrador")).toBeInTheDocument();
    expect(screen.queryByText("Para revisar")).not.toBeInTheDocument();
    expect(screen.queryByText(/Falta el copy/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Me gusta: no disponible" }));
    expect(toast).toHaveBeenCalledWith(expect.stringMatching(/no está en revisión|entra sola/i));
  });

  it("el dislike se muestra en TODA pieza en revisión, aunque no te toque decidir (fila estable)", async () => {
    // Cadena vacía (sin niveles): `puedeDar` es false, pero el botón existe igualmente; al
    // pulsarlo, un toast explica (no desaparece y baila entre tarjetas).
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ niveles: [], estado: "sin_cadena", nivel_actual: "", aprobados: 0, minimo_aprobaciones: 0, comentarios_sin_resolver: 0 }),
          { status: 200 },
        ),
      ),
    );
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    expect(await screen.findByRole("button", { name: "No me gusta" })).toBeInTheDocument();
  });

  it("aprobar que CIERRA la cadena confirma 'lista para publicar' y ofrece Deshacer", async () => {
    stubFetchAprobacion("aprobado");
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    // Espera la cadena (el panel pinta el conteo 0/1) para que el like sea elegible.
    expect(await screen.findByText("0/1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dale tu OK" }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Pieza aprobada: lista para publicar.",
        expect.objectContaining({ action: expect.objectContaining({ label: "Deshacer" }) }),
      ),
    );
  });

  it("aprobar con OK parcial (la pieza sigue en revisión) NO miente y ofrece Deshacer", async () => {
    stubFetchAprobacion("en_revision");
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    expect(await screen.findByText("0/1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dale tu OK" }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Tu OK quedó registrado; falta el de otra persona.",
        expect.objectContaining({ action: expect.objectContaining({ label: "Deshacer" }) }),
      ),
    );
  });

  it("el segundo like DESHACE tu OK (toggle estándar), sin ofrecer «Forzar»", async () => {
    // Cadena con TU OK ya dado (decisor u1): el botón pasa a "Quitar tu OK".
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        urls.push(ruta);
        if (ruta.includes("/deshacer")) {
          return new Response(
            JSON.stringify({ publicacion: pub({ estado: "en_revision" }) }),
            { status: 200 },
          );
        }
        if (ruta.includes("/aprobacion")) {
          return new Response(
            JSON.stringify({
              niveles: [
                {
                  id: "n1",
                  plataforma_id: "p1",
                  contenido_id: "c1",
                  nivel: 1,
                  etiqueta: "Edición",
                  decision: "aprobado",
                  decisor_id: "u1",
                  decisor_nombre: "Revisor",
                  comentario: "",
                  creado: "",
                  decidido_en: "",
                  cargo_requerido: "",
                },
              ],
              estado: "pendiente",
              nivel_actual: "",
              aprobados: 1,
              minimo_aprobaciones: 0,
              comentarios_sin_resolver: 0,
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    const like = await screen.findByRole("button", { name: "Quitar tu OK" });
    fireEvent.click(like);
    // Toggle de verdad: POST /deshacer y toast "Quitamos tu OK." (nada de "Forzar" a un toque).
    await waitFor(() => expect(urls.some((u) => u.includes("/deshacer"))).toBe(true));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Quitamos tu OK."));
    expect(toast).not.toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ action: expect.objectContaining({ label: "Forzar" }) }),
    );
  });

  it("«Forzar» vive como botón discreto del panel (admin), no en el toast del like", async () => {
    stubFetchAprobacion("aprobado");
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }), { rol: "admin" });
    expect(await screen.findByText("0/1")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Forzar aprobación (saltar la cadena)" }),
    ).toBeInTheDocument();
  });

  it("orden de gates: el autor con comentarios sin resolver recibe el motivo de elegibilidad", async () => {
    // Cadena con nivel humano pendiente + 2 comentarios sin resolver, pero el usuario u1 es el
    // AUTOR: el toast explica que no puede dar OK a su pieza, NO le manda a resolver comentarios
    // de un OK que no puede dar.
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/aprobacion")) {
          return new Response(
            JSON.stringify({
              niveles: [
                {
                  id: "n1",
                  plataforma_id: "p1",
                  contenido_id: "c1",
                  nivel: 1,
                  etiqueta: "Edición",
                  decision: "pendiente",
                  decisor_id: "",
                  decisor_nombre: "",
                  comentario: "",
                  creado: "",
                  decidido_en: "",
                  cargo_requerido: "",
                },
              ],
              estado: "pendiente",
              nivel_actual: "n1",
              aprobados: 0,
              minimo_aprobaciones: 0,
              comentarios_sin_resolver: 2,
            }),
            { status: 200 },
          );
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar", autor_id: "u1" }));
    // Espera a que la cadena cargue (el aviso de comentarios aparece en el panel).
    expect(await screen.findByText(/Falta resolver 2 comentarios/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Me gusta: no disponible" }));
    expect(toast).toHaveBeenCalledWith(expect.stringMatching(/tu propia pieza/i));
    expect(toast).not.toHaveBeenCalledWith(expect.stringMatching(/Resuelve/));
  });

  it("cadena que falla (500): franja con «Reintentar» y el like explica el error, no el turno", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/aprobacion")) {
          return new Response(JSON.stringify({ error: "boom" }), { status: 500 });
        }
        return new Response("{}", { status: 200 });
      }),
    );
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    expect(
      await screen.findByText("No se pudo cargar el estado de aprobación."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Reintentar" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Me gusta: no disponible" }));
    expect(toast).toHaveBeenCalledWith(
      expect.stringMatching(/No se pudo cargar el estado de aprobación/),
    );
    expect(toast).not.toHaveBeenCalledWith(expect.stringMatching(/Espera tu turno/));
  });

  it("editar una pieza PUBLICADA avisa con el mensaje específico (ya salió a la red)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("{}", { status: 200 })),
    );
    renderPost(pub({ estado: "publicado", etapa_ia: "publicada" }));
    fireEvent.click(screen.getByRole("button", { name: /abrir para editar/i }));
    expect(await screen.findByText(/ya salió a la red/i)).toBeInTheDocument();
  });
});
