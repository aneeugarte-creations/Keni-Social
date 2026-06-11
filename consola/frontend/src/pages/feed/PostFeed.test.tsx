import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { toast } from "sonner";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ContenedorConfirmacion } from "@/components/comunes/ContenedorConfirmacion";
import { SesionContexto, type ValorSesion } from "@/hooks/sesion-contexto";
import { MarcaActivaProvider } from "@/hooks/use-marca-activa";
import { formatearFechaHora, formatearFechaHoraCorta } from "@/lib/fecha";
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
  const res = render(
    <MemoryRouter>
      <QueryClientProvider client={client}>
        <SesionContexto.Provider value={valor}>
          {/* Comentarios (el hilo en línea) consume la marca activa. */}
          <MarcaActivaProvider>
            <PostFeed publicacion={publicacion} />
            {/* La confirmación imperativa (`confirmar`) necesita su contenedor montado. */}
            <ContenedorConfirmacion />
          </MarcaActivaProvider>
        </SesionContexto.Provider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  // `client` expuesto para espiar invalidaciones de caché (p. ej. los conteos de pestañas).
  return { ...res, client };
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
    expect(enlace).toHaveAttribute("href", "/datos/produccion/pipelines/c1");
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

  it("pieza completa aún fuera de revisión: badge 'Para revisar' (sin etapa intermedia) y like avisa que entra sola", () => {
    renderPost(pub({ etapa_ia: "lista_para_revisar" }));
    // Una pieza completa se pinta directa como "Para revisar": el pipeline la avanza sola a la
    // cola de revisión, así que «borrador» no es un estado donde descanse y no hay badge aparte.
    expect(screen.getByText("Para revisar")).toBeInTheDocument();
    expect(screen.queryByText("En borrador")).not.toBeInTheDocument();
    expect(screen.queryByText(/Falta el copy/i)).not.toBeInTheDocument();
    // Mientras el avance no la ha movido todavía (estado aún borrador), el like avisa que entra
    // sola: el gate humano (los OK) se abre en cuanto está en la cola.
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

  it("«Forzar» NO es un botón de la tarjeta: se ofrece en el toast del primer OK (admin)", async () => {
    stubFetchAprobacion("aprobado");
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }), { rol: "admin" });
    expect(await screen.findByText("0/1")).toBeInTheDocument();
    // La tarjeta queda limpia: ni el panel ni la fila de acciones ofrecen el override.
    expect(screen.queryByRole("button", { name: /forzar/i })).not.toBeInTheDocument();
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

  it("el like SIN pulsar va en gris de reposo (nada de acento rojo de marca)", async () => {
    stubFetchAprobacion("aprobado");
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    const like = await screen.findByRole("button", { name: "Dale tu OK" });
    // El acento keni (#d12d07) se leía como un like ROJO sin pulsar; el color queda
    // reservado al estado pulsado (verde = tu OK puesto).
    expect(like.className).not.toContain("text-keni");
    expect(like.className).toContain("text-muted-foreground");
  });

  it("el «Deshacer» del toast de aprobar retira el OK (origen 'ok'), no un dislike genérico", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        urls.push(ruta);
        // OJO al orden: /aprobacion/p1/deshacer contiene también "/aprobacion".
        if (ruta.includes("/deshacer")) {
          return new Response(
            JSON.stringify({ publicacion: pub({ estado: "en_revision" }) }),
            { status: 200 },
          );
        }
        if (ruta.includes("/aprobar")) {
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
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    fireEvent.click(await screen.findByRole("button", { name: "Dale tu OK" }));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Tu OK quedó registrado; falta el de otra persona.",
        expect.objectContaining({ action: expect.objectContaining({ label: "Deshacer" }) }),
      ),
    );
    // Ejecuta el Deshacer del toast: debe llamar a /deshacer y confirmar "Quitamos tu OK."
    // (no el genérico "Quitamos tu reacción." de un dislike).
    const llamada = (toast.success as unknown as ReturnType<typeof vi.fn>).mock.calls.find(
      (c) => c[1]?.action?.label === "Deshacer",
    );
    (llamada?.[1] as { action: { onClick: () => void } }).action.onClick();
    await waitFor(() => expect(urls.some((u) => u.includes("/deshacer"))).toBe(true));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Quitamos tu OK."));
  });

  it("pieza APROBADA: sin botón de like (falso affordance) y con el último OK como metadato", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({ niveles: [], estado: "sin_cadena", nivel_actual: "", aprobados: 0, minimo_aprobaciones: 0, comentarios_sin_resolver: 0 }),
          { status: 200 },
        ),
      ),
    );
    renderPost(pub({ estado: "aprobado", etapa_ia: "aprobada", revisor_nombre: "Leo" }));
    // Nada de un Check enfocable que solo lanza un toast: el botón no existe.
    expect(screen.queryByRole("button", { name: /me gusta/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /tu ok/i })).not.toBeInTheDocument();
    // El dato del último OK (antes solo en el title del Check) queda legible.
    expect(screen.getByText("OK: Leo")).toBeInTheDocument();
    expect(screen.getByTitle("Último OK")).toBeInTheDocument();
    // Comentar sigue disponible.
    expect(screen.getByRole("button", { name: "Comentar" })).toBeInTheDocument();
  });

  it("fecha de salida: neutra (el ámbar lo porta el badge) y, programada, es el puente a Programación", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    const fecha = "2026-06-12T10:00:00Z";
    const corta = formatearFechaHoraCorta(fecha);
    const completa = formatearFechaHora(fecha); // el hover/nombre lleva el dato COMPLETO (con año)
    const { unmount } = renderPost(
      pub({ estado: "programado", etapa_ia: "programada", fecha_programada: fecha }),
    );
    // Programada: la fecha enlaza a la página de Programación (tratamiento discreto, sin
    // duplicar el ámbar que ya lleva el badge de etapa).
    const enlace = screen.getByRole("link", {
      name: `Programada para ${completa} — ver en Programación`,
    });
    expect(enlace).toHaveAttribute("href", "/operacion/programacion");
    expect(enlace).toHaveTextContent(corta);
    expect(enlace.className).toContain("text-muted-foreground");
    expect(enlace.className).not.toContain("amber");
    unmount();
    renderPost(pub({ estado: "publicado", etapa_ia: "publicada", fecha_programada: fecha }));
    // Publicada: span inerte (no hay a dónde ir), con la fecha completa en title y sr-only.
    expect(screen.getByText(`Publicada el ${completa}`)).toBeInTheDocument();
    expect(screen.getByTitle(`Publicada el ${completa}`).className).toContain("text-muted-foreground");
    expect(screen.queryByRole("link", { name: /Programación/ })).not.toBeInTheDocument();
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

  it("el metadato del último OK trunca (no desborda la celda con nombres largos)", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    renderPost(
      pub({
        estado: "aprobado",
        etapa_ia: "aprobada",
        revisor_nombre: "Coordinadora Editorial Larguísima De Verdad",
      }),
    );
    const ok = screen.getByTitle("Último OK");
    expect(ok.className).toContain("truncate");
    expect(ok.className).toContain("max-w-[12rem]");
  });

  it("el dislike DECISIVO pide confirmación (los OK se pierden) antes de rechazar", async () => {
    // Cadena de UN nivel humano: el umbral de rechazo es 1, así que el primer dislike ya es
    // decisivo. OJO al orden del stub: /aprobacion/p1/rechazar contiene también "/aprobacion".
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        urls.push(ruta);
        if (ruta.includes("/rechazar")) {
          return new Response(
            JSON.stringify({ publicacion: pub({ estado: "borrador" }) }),
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
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    expect(await screen.findByText("0/1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "No me gusta" }));
    // El confirm de la casa, ANTES de pedir nada al backend.
    expect(await screen.findByText("Rechazar la pieza")).toBeInTheDocument();
    expect(urls.some((u) => u.includes("/rechazar"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Rechazar" }));
    await waitFor(() => expect(urls.some((u) => u.includes("/rechazar"))).toBe(true));
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith("Pieza rechazada: vuelve a redacción."),
    );
  });

  it("el PRIMER dislike (no decisivo) va directo y abre el hilo para apuntar el motivo", async () => {
    // Cadena de DOS niveles humanos sin dislikes: el primero NO es decisivo (umbral 2):
    // ni confirmación ni fricción, pero el hilo se abre (la objeción necesita su porqué).
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
        if (ruta.includes("/rechazar")) {
          return new Response(
            JSON.stringify({ publicacion: pub({ estado: "en_revision" }) }),
            { status: 200 },
          );
        }
        if (ruta.includes("/comentarios")) {
          return new Response(JSON.stringify({ comentarios: [], total: 0 }), { status: 200 });
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
                {
                  id: "n2",
                  plataforma_id: "p1",
                  contenido_id: "c1",
                  nivel: 2,
                  etiqueta: "Coordinación",
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
    renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    expect(await screen.findByText("0/2")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "No me gusta" }));
    // Sin confirmación (caso común, cero fricción)…
    expect(screen.queryByText("Rechazar la pieza")).not.toBeInTheDocument();
    // …el toast cuenta el desenlace real con Deshacer y el hilo queda abierto con el
    // textarea a mano.
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Dislike registrado; con un segundo dislike la pieza se rechaza.",
        expect.objectContaining({ action: expect.objectContaining({ label: "Deshacer" }) }),
      ),
    );
    expect(
      await screen.findByPlaceholderText(/escribe un comentario/i),
    ).toBeInTheDocument();
  });

  it("dislike con tu OK puesto: el toast trae la acción directa «Quitar mi OK» (toggle simétrico)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string | URL) => {
        const ruta = String(url);
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
    // Con TU OK puesto el like es "Quitar tu OK"; el dislike no destruye nada por sí solo.
    expect(await screen.findByRole("button", { name: "Quitar tu OK" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "No me gusta" }));
    expect(toast).toHaveBeenCalledWith(
      "Tu OK está puesto; vuelve a pulsar «Me gusta» para quitarlo.",
      expect.objectContaining({ action: expect.objectContaining({ label: "Quitar mi OK" }) }),
    );
  });

  it("sin contenido_id, Comentar queda visible pero DESHABILITADO y lo explica", () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));
    renderPost(pub({ contenido_id: "" }));
    const boton = screen.getByRole("button", {
      name: "Esta pieza no tiene hilo de comentarios",
    });
    expect(boton).toBeDisabled();
  });

  it("una reacción que CAMBIA el estado invalida los conteos de las pestañas (el badge no miente)", async () => {
    stubFetchAprobacion("aprobado"); // la pieza pasa de en_revision -> aprobado
    const { client } = renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    const spy = vi.spyOn(client, "invalidateQueries");
    expect(await screen.findByText("0/1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dale tu OK" }));
    await waitFor(() =>
      expect(
        spy.mock.calls.some((c) =>
          JSON.stringify((c[0] as { queryKey?: unknown })?.queryKey ?? []).includes("conteo-feed"),
        ),
      ).toBe(true),
    );
  });

  it("una reacción que NO cambia el estado deja los conteos en paz (3 fetch ahorrados)", async () => {
    stubFetchAprobacion("en_revision"); // OK parcial: la pieza sigue en revisión
    const { client } = renderPost(pub({ estado: "en_revision", etapa_ia: "lista_para_revisar" }));
    const spy = vi.spyOn(client, "invalidateQueries");
    expect(await screen.findByText("0/1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dale tu OK" }));
    await waitFor(() => expect(toast.success).toHaveBeenCalled());
    expect(
      spy.mock.calls.some((c) =>
        JSON.stringify((c[0] as { queryKey?: unknown })?.queryKey ?? []).includes("conteo-feed"),
      ),
    ).toBe(false);
  });
});
