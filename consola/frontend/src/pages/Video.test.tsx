/**
 * Tests de Video (editor REAL del "toque RRSS"):
 *  - Renderiza el header "Editor de video" y la sub-navegación de secciones.
 *  - La sección Base muestra el selector de formato (9:16/1:1/16:9) y la zona de subida.
 *  - Las secciones Overlay/PiP/Subtítulos/Render están deshabilitadas hasta subir un clip base.
 *  - El selector de formato es accesible (radiogroup) con 9:16 marcado por defecto.
 *
 * No se ejercita el editor de capas (Konva) ni el render real: eso es preview/server-side.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProveedorEncabezado } from "@/components/layout/encabezado";
import * as apiMod from "@/lib/api";
import { pistaPip, setClipPip, type ComposicionVideo } from "@/lib/video";

import Video from "./Video";

// Marca activa: la página solo lee `marcaActiva`/`marcaPrimaria`. Mutable por test (el caso
// "sin marca" la vacía) y se restaura en cada beforeEach.
const marcaMock = vi.hoisted(() => ({
  actual: { marcaActiva: "unotv", marcaPrimaria: "unotv" } as {
    marcaActiva: string | null;
    marcaPrimaria: string | null;
  },
}));
vi.mock("@/hooks/marca-activa-contexto", () => ({
  useMarcaActiva: () => marcaMock.actual,
}));

// Stub de red genérico (la query de formatos cae al fallback local con retry:false).
vi.stubGlobal("fetch", vi.fn(async () => new Response("{}", { status: 200 })));

function docConBase(): ComposicionVideo {
  return {
    version: 1,
    marca: "unotv",
    formato: { w: 1080, h: 1920, fps: 30, preset: "9:16" },
    duracion_ms: 30000,
    pistas: [
      {
        id: "base",
        tipo: "video",
        clips: [
          {
            id: "c1",
            media_id: "videos/abc.mp4",
            inicio_ms: 0,
            fin_ms: 30000,
            recorte_in_ms: 0,
            recorte_out_ms: 30000,
            x: 0,
            y: 0,
            w: 1080,
            h: 1920,
            ajuste: "cover",
            foco: [0.5, 0.5],
          },
        ],
      },
      { id: "pip", tipo: "video", clips: [] },
      { id: "overlay", tipo: "overlay", capas: [] },
      {
        id: "subs",
        tipo: "subtitulos",
        subtitulo_id: "",
        estilo: { fuente: "Barlow", tam: 64, color: "#FFF", borde: "#000", posicion: "inferior", karaoke: true },
      },
    ],
  };
}

function renderVideo(rutaInicial = "/contenido/video") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[rutaInicial]}>
        <Video />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("Video", () => {
  beforeEach(() => {
    marcaMock.actual = { marcaActiva: "unotv", marcaPrimaria: "unotv" };
    // El gestor (sección por defecto) lista composiciones + piezas: stubs vacíos por defecto.
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({ composiciones: [] });
    vi.spyOn(apiMod.api, "piezas").mockResolvedValue({
      piezas: [],
      paginacion: { total: 0, limite: 0, desplazamiento: 0 },
    } as never);
    vi.spyOn(apiMod.api.video, "subtitulosDe").mockResolvedValue({ subtitulo: null });
  });

  afterEach(() => vi.restoreAllMocks());

  // Lleva del gestor (sección por defecto) a la sección Base.
  function irABase() {
    fireEvent.click(screen.getByRole("button", { name: /^base$/i }));
  }

  it("muestra el título de sección 'Video'", () => {
    renderVideo();
    // El título vive en la cabecera unificada (`TituloPagina`); en tests sin AppShell
    // cae a render inline, así que el texto "Video" está presente.
    expect(screen.getAllByText("Video").length).toBeGreaterThan(0);
  });

  it("arranca en el GESTOR de composiciones ('Mis composiciones')", () => {
    renderVideo();
    // El encabezado del gestor (h2) y el botón de nueva composición.
    expect(screen.getByRole("button", { name: /nueva composición/i })).toBeInTheDocument();
  });

  it("muestra el selector de formato con 9:16 seleccionado por defecto (sección Base)", async () => {
    renderVideo();
    await irABase();
    const grupo = screen.getByRole("radiogroup", { name: /formato de video/i });
    expect(grupo).toBeInTheDocument();
    const vertical = screen.getByRole("radio", { name: /9:16/i });
    expect(vertical).toHaveAttribute("aria-checked", "true");
  });

  it("muestra la zona de carga del clip base (EditorVideo reutilizado)", async () => {
    renderVideo();
    await irABase();
    expect(screen.getByText(/subir video/i)).toBeInTheDocument();
  });

  it("deshabilita las secciones que requieren clip base (Render, Subtítulos) CON la razón", () => {
    renderVideo();
    // Las pestañas son botones; sin clip base, Render/Subtítulos están deshabilitadas y el
    // `title` explica el porqué (un disabled mudo desorienta).
    const render = screen.getByRole("button", { name: /^render$/i });
    const subs = screen.getByRole("button", { name: /subtítulos/i });
    expect(render).toBeDisabled();
    expect(render).toHaveAttribute("title", "Requiere un clip base");
    expect(subs).toBeDisabled();
    expect(subs).toHaveAttribute("title", "Requiere un clip base");
    // Las secciones Base y "Mis composiciones" sí están activas (y sin tooltip de bloqueo).
    const base = screen.getByRole("button", { name: /^base$/i });
    expect(base).not.toBeDisabled();
    expect(base).not.toHaveAttribute("title");
    expect(screen.getByRole("button", { name: /mis composiciones/i })).not.toBeDisabled();
  });

  it("sin marca activa: aviso claro y edición desactivada (no un toast al primer cambio)", () => {
    marcaMock.actual = { marcaActiva: null, marcaPrimaria: null };
    renderVideo();
    irABase();
    expect(screen.getByRole("alert")).toHaveTextContent(/selecciona una marca arriba/i);
    // La edición queda desactivada hasta elegir marca: formato, título y guardar borrador.
    expect(screen.getByRole("radio", { name: /9:16/i })).toBeDisabled();
    expect(screen.getByLabelText(/título del borrador/i)).toBeDisabled();
    expect(screen.getByRole("button", { name: /guardar borrador/i })).toBeDisabled();
  });

  it("con marca activa no hay aviso de marca y la edición está habilitada", () => {
    renderVideo();
    irABase();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /9:16/i })).not.toBeDisabled();
    expect(screen.getByRole("button", { name: /guardar borrador/i })).not.toBeDisabled();
  });

  it("avisa que el preview es aproximado (render fiel = servidor)", async () => {
    renderVideo();
    await irABase();
    expect(screen.getByText(/preview aproximado/i)).toBeInTheDocument();
  });

  it("carga una composición existente por `?composicion=<id>`", async () => {
    const composicion = vi
      .spyOn(apiMod.api.video, "composicion")
      .mockResolvedValue({
        composicion: { id: "comp-7", documento: docConBase(), titulo: "Mi clip", estado: "borrador" },
      });
    renderVideo("/contenido/video?composicion=comp-7");
    // Tras cargar, abre la sección Base con el clip ya presente: el reencuadre (que exige base)
    // y las secciones que requieren base quedan habilitadas.
    await waitFor(() => expect(composicion).toHaveBeenCalledWith("comp-7"));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^render$/i })).not.toBeDisabled(),
    );
  });

  it("con clip base muestra la LÍNEA DE TIEMPO (regla + playhead + asas de trim)", async () => {
    vi.spyOn(apiMod.api.video, "composicion").mockResolvedValue({
      composicion: { id: "comp-7", documento: docConBase(), titulo: "Mi clip", estado: "borrador" },
    });
    renderVideo("/contenido/video?composicion=comp-7");
    // El timeline vive bajo el preview: playhead accesible y asas de trim del clip base.
    await waitFor(() =>
      expect(screen.getByLabelText("Línea de tiempo de la composición")).toBeInTheDocument(),
    );
    expect(screen.getByRole("slider", { name: /cursor de reproducción/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recortar inicio del clip/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /recortar fin del clip/i })).toBeInTheDocument();
  });

  it("por `?contenido=<id>` REABRE la composición de la pieza si ya existe", async () => {
    const listar = vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({
      composiciones: [
        {
          id: "comp-existente",
          publicacion_id: "cont-5",
          marca: "unotv",
          marca_nombre: "UnoTV",
          titulo: "Pieza ligada",
          estado: "borrador",
          creado: "",
          actualizado: "",
          documento: docConBase(),
        },
      ],
    });
    const crear = vi.spyOn(apiMod.api.video, "crearComposicion");
    renderVideo("/contenido/video?contenido=cont-5");
    await waitFor(() =>
      expect(listar).toHaveBeenCalledWith({ marca: "unotv", publicacion_id: "cont-5" }),
    );
    // Existía: NO crea una nueva.
    expect(crear).not.toHaveBeenCalled();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^render$/i })).not.toBeDisabled(),
    );
  });

  it("por `?contenido=<id>` CREA una composición ligada si no existe (find-or-create)", async () => {
    vi.spyOn(apiMod.api.video, "listarComposiciones").mockResolvedValue({ composiciones: [] });
    const crear = vi
      .spyOn(apiMod.api.video, "crearComposicion")
      .mockResolvedValue({ id: "comp-nueva" });
    renderVideo("/contenido/video?contenido=cont-9");
    await waitFor(() => expect(crear).toHaveBeenCalledTimes(1));
    // La nueva composición se crea LIGADA a la pieza (publicacion_id) y con título por defecto.
    expect(crear.mock.calls[0][0]).toMatchObject({
      marca: "unotv",
      publicacion_id: "cont-9",
      estado: "borrador",
    });
    expect(crear.mock.calls[0][0].titulo).toMatch(/^Borrador/);
  });

  it("CREA el borrador al PRIMER cambio significativo (cambiar de formato), sin clip base", async () => {
    const crear = vi
      .spyOn(apiMod.api.video, "crearComposicion")
      .mockResolvedValue({ id: "comp-temprana" });
    renderVideo();
    irABase();
    // Cambiar el formato a 1:1 es una edición real del documento → crea el borrador.
    fireEvent.click(screen.getByRole("radio", { name: /1:1/i }));
    await waitFor(() => expect(crear).toHaveBeenCalledTimes(1));
    // Sin clip base: la creación NO esperó al clip. Título por defecto derivado.
    expect(crear.mock.calls[0][0].titulo).toMatch(/^Borrador/);
  });

  it("el indicador de guardado se PORTALIZA a la cabecera unificada (AccionesPagina)", () => {
    // Hueco de acciones de la barra superior, como lo montaría el AppShell.
    const slot = document.createElement("div");
    document.body.appendChild(slot);
    try {
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      render(
        <QueryClientProvider client={client}>
          <ProveedorEncabezado
            value={{ slotInicio: null, slotAcciones: slot, registrarTitulo: () => () => {} }}
          >
            <MemoryRouter initialEntries={["/contenido/video"]}>
              <Video />
            </MemoryRouter>
          </ProveedorEncabezado>
        </QueryClientProvider>,
      );
      // En el gestor (sección por defecto) no se edita un borrador: sin indicador.
      expect(within(slot).queryByText(/sin guardar/i)).not.toBeInTheDocument();
      irABase();
      // En una sección de edición el indicador aterriza en el hueco de la cabecera.
      expect(within(slot).getByText(/sin guardar/i)).toBeInTheDocument();
    } finally {
      slot.remove();
    }
  });

  it("el botón 'Guardar borrador' crea la composición y muestra 'Guardado'", async () => {
    const crear = vi
      .spyOn(apiMod.api.video, "crearComposicion")
      .mockResolvedValue({ id: "comp-guardada" });
    renderVideo();
    irABase();
    expect(screen.getByText(/sin guardar/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /guardar borrador/i }));
    await waitFor(() => expect(crear).toHaveBeenCalledTimes(1));
    expect(await screen.findByText(/^Guardado$/)).toBeInTheDocument();
  });

  it("el commit del trim AUTOGUARDA (PUT) y el indicador pasa por 'Guardando…' → 'Guardado'", async () => {
    vi.spyOn(apiMod.api.video, "composicion").mockResolvedValue({
      composicion: { id: "comp-7", documento: docConBase(), titulo: "T", estado: "borrador" },
    });
    // PUT controlable: así se puede asertar el "Guardando…" mientras la escritura está en curso.
    let resolverPut: () => void = () => {};
    const put = vi
      .spyOn(apiMod.api.video, "guardarComposicion")
      .mockImplementation(
        () => new Promise<never>((res) => { resolverPut = () => res({} as never); }),
      );
    renderVideo("/contenido/video?composicion=comp-7");
    const asa = await screen.findByRole("button", { name: /recortar fin del clip/i });
    // jsdom no tiene layout: banda de 100px (1px = 1% del eje de 30 s).
    const banda = screen.getByLabelText("Línea de tiempo de la composición");
    vi.spyOn(banda, "getBoundingClientRect").mockReturnValue({
      left: 0, top: 0, width: 100, height: 96, right: 100, bottom: 96, x: 0, y: 0, toJSON: () => ({}),
    } as DOMRect);
    fireEvent.mouseDown(asa, { clientX: 100 });
    fireEvent.mouseMove(window, { clientX: 50 });
    fireEvent.mouseUp(window); // commit del trim → autoguardado
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0][0]).toBe("comp-7");
    const guardado = put.mock.calls[0][1] as ComposicionVideo;
    const clip = (guardado.pistas[0] as { clips: { recorte_out_ms?: number }[] }).clips[0];
    expect(clip.recorte_out_ms).toBe(15000);
    // Feedback del autoguardado: "Guardando…" en curso y "Guardado" al asentar.
    expect(screen.getByText("Guardando…")).toBeInTheDocument();
    await act(async () => resolverPut());
    expect(await screen.findByText(/^Guardado$/)).toBeInTheDocument();
  });

  it("lo editado MIENTRAS se creaba el borrador se guarda al terminar la creación (flush)", async () => {
    // Creación controlable: el segundo cambio llega con el POST aún en curso.
    let resolverCrear: () => void = () => {};
    const crear = vi.spyOn(apiMod.api.video, "crearComposicion").mockImplementation(
      () => new Promise<{ id: string }>((res) => { resolverCrear = () => res({ id: "comp-nueva" }); }),
    );
    const put = vi.spyOn(apiMod.api.video, "guardarComposicion").mockResolvedValue({} as never);
    renderVideo();
    irABase();
    fireEvent.click(screen.getByRole("radio", { name: "1:1" })); // primer cambio → crea (en curso)
    await waitFor(() => expect(crear).toHaveBeenCalledTimes(1));
    await act(async () => {}); // deja propagar el isPending de la creación
    fireEvent.click(screen.getByRole("radio", { name: "16:9" })); // edición DURANTE la creación
    expect(crear).toHaveBeenCalledTimes(1); // no re-crea: la creación sigue en curso
    expect(put).not.toHaveBeenCalled(); // sin id todavía no hay dónde guardar
    await act(async () => resolverCrear());
    // Al llegar el id se FLUSHEA el doc vigente: el 16:9 no se pierde (antes quedaba solo local).
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    expect(put.mock.calls[0][0]).toBe("comp-nueva");
    expect((put.mock.calls[0][1] as ComposicionVideo).formato.preset).toBe("16:9");
  });

  it("arrastrar el PiP en el preview SINCRONIZA los inputs numéricos y autoguarda (y viceversa)", async () => {
    // Composición con base + PiP por defecto (x=673, y=1674, w=367, h=206 en el lienzo 9:16).
    const docPip = setClipPip(docConBase(), "videos/pip.mp4", 10000);
    vi.spyOn(apiMod.api.video, "composicion").mockResolvedValue({
      composicion: { id: "comp-7", documento: docPip, titulo: "T", estado: "borrador" },
    });
    const put = vi.spyOn(apiMod.api.video, "guardarComposicion").mockResolvedValue({} as never);
    renderVideo("/contenido/video?composicion=comp-7");
    const tabPip = await screen.findByRole("button", { name: /^pip$/i });
    await waitFor(() => expect(tabPip).not.toBeDisabled());
    fireEvent.click(tabPip);
    // La caja del preview SOLO es interactiva en la sección PiP.
    const caja = await screen.findByRole("group", { name: "Ventana PiP" });
    // Arrastre: Δpantalla (−20, −10) a escala 520/1920 = Δlienzo (−73,8, −36,9) → (599, 1637).
    fireEvent.mouseDown(caja, { clientX: 500, clientY: 500 });
    fireEvent.mouseMove(window, { clientX: 480, clientY: 490 });
    fireEvent.mouseUp(window);
    // El commit fluye al MISMO doc que alimenta el panel: los inputs reflejan la nueva posición…
    expect(screen.getByLabelText("PiP X")).toHaveValue(599);
    expect(screen.getByLabelText("PiP Y")).toHaveValue(1637);
    // …y se autoguarda (PUT con la caja movida).
    await waitFor(() => expect(put).toHaveBeenCalledTimes(1));
    const guardado = put.mock.calls[0][1] as ComposicionVideo;
    expect(pistaPip(guardado)!.clips[0]).toMatchObject({ x: 599, y: 1637, w: 367, h: 206 });
    // Y al revés: editar el input numérico recoloca la caja del preview (sincronía bidireccional).
    fireEvent.change(screen.getByLabelText("PiP X"), { target: { value: "100" } });
    expect(caja.style.left).toBe(`${100 * (520 / 1920)}px`);
  });

  it("'Marcar listo' hace PUT del estado='listo' sin reenviar documento", async () => {
    vi.spyOn(apiMod.api.video, "composicion").mockResolvedValue({
      composicion: { id: "comp-7", documento: docConBase(), titulo: "T", estado: "borrador" },
    });
    const actualizar = vi
      .spyOn(apiMod.api.video, "actualizarComposicion")
      .mockResolvedValue({ composicion: { id: "comp-7", titulo: "T", estado: "listo" } });
    renderVideo("/contenido/video?composicion=comp-7");
    const boton = await screen.findByRole("button", { name: /marcar listo/i });
    fireEvent.click(boton);
    await waitFor(() => expect(actualizar).toHaveBeenCalledWith("comp-7", { estado: "listo" }));
  });
});
