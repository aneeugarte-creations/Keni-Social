/**
 * Tests del panel de OVERLAY de video (plantillas compartidas con Imagen):
 *  - «Plantillas» abre la MISMA galería (GaleriaPlantillas) filtrada por la marca y aplicar una
 *    es 1 clic: las capas llegan al padre adaptadas al formato del video y SIN huecos de foto.
 *  - «Guardar como plantilla…» persiste el overlay como PlantillaDiseno de la marca (con el
 *    hueco de foto oculto que exige el servidor) — paridad bidireccional con Imagen.
 *  - Con el overlay vacío no se ofrece guardar (aviso, sin diálogo).
 *
 * El editor de capas real (Konva) NO se monta: se mockea EditorDocumento y se ejercita solo el
 * cableado de plantillas (galería, adaptación, guardado).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  documentoVacio,
  nuevaCapaImagen,
  nuevaCapaTexto,
  type Capa,
  type CapaImagen,
  type Documento,
} from "@/editor/documento";
import * as apiMod from "@/lib/api";
import type { PlantillaDiseno } from "@/lib/api";
import { PRESETS_FORMATO_VIDEO, type ClipVideo, type ComposicionVideo } from "@/lib/video";

import { documentoOverlay, PanelOverlay } from "./PanelOverlay";

// El editor real arrastra Konva (canvas): aquí solo importa el cableado de plantillas, así que se
// sustituye por un stub que expone el botón del rail («Plantillas»), las entradas de `menuExtra`
// y el fondo del lienzo (`fondoLienzo`) para que FondoVideo se pueda ejercitar.
vi.mock("@/editor/EditorDocumento", () => ({
  EditorDocumento: ({
    onPlantillas,
    menuExtra,
    fondoLienzo,
  }: {
    onPlantillas?: () => void;
    menuExtra?: ReactNode;
    fondoLienzo?: ReactNode;
  }) => (
    <div>
      <button onClick={onPlantillas}>Plantillas</button>
      <div>{menuExtra}</div>
      <div>{fondoLienzo}</div>
    </div>
  ),
}));

function docVideo(): ComposicionVideo {
  return {
    version: 1,
    marca: "unotv",
    formato: { w: 1080, h: 1920, fps: 30, preset: "9:16" },
    duracion_ms: 30000,
    pistas: [
      { id: "base", tipo: "video", clips: [] },
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

/** Plantilla 4:5 de Imagen: hueco de foto a sangre + un titular. */
function plantilla(): PlantillaDiseno {
  const documento = documentoVacio({ w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 }, "unotv");
  documento.capas = [
    nuevaCapaImagen("", { x: 0, y: 0, w: 1080, h: 1350, z: 0, es_foto: true, visible: true }),
    nuevaCapaTexto({ x: 80, y: 1100, w: 920, h: 160, z: 10, texto: "Titular" }),
  ];
  return {
    id: "pl-1",
    marca: "unotv",
    nombre: "Placa",
    categoria: "post",
    tipo: "foto",
    documento,
    miniatura: "",
    miniatura_url: "",
    foto_muestra: "",
    foto_muestra_url: "",
    titular_muestra: "",
    etiqueta_muestra: "",
    categorias: [],
    activo: true,
    rotar: false,
    orden: 0,
    marca_nombre: "UnoTV",
    autor_id: "",
    autor_nombre: "",
    creado: "2026-06-01T10:00:00Z",
    actualizado: "2026-06-01T10:00:00Z",
  };
}

function renderPanel(capas: Capa[] = [], onCapas = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <PanelOverlay doc={docVideo()} marca="unotv" capas={capas} onCapas={onCapas} />
    </QueryClientProvider>,
  );
  return onCapas;
}

/** Composición con un clip base real que tiene `recorte_in_ms` configurable. */
function docVideoConClip(recorteInMs = 0): ComposicionVideo {
  const clip: ClipVideo = {
    id: "c1",
    media_id: "videos/x.mp4",
    inicio_ms: 0,
    fin_ms: 5000,
    recorte_in_ms: recorteInMs,
    recorte_out_ms: 5000,
    x: 0,
    y: 0,
    w: 1080,
    h: 1920,
    ajuste: "cover",
    foco: [0.5, 0.5],
  };
  return {
    ...docVideo(),
    pistas: [
      { id: "base", tipo: "video", clips: [clip] },
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

beforeEach(() => {
  vi.spyOn(apiMod.api, "plantillasDiseno").mockResolvedValue({ plantillas: [plantilla()] });
});

afterEach(() => vi.restoreAllMocks());

describe("PanelOverlay · plantillas compartidas con Imagen", () => {
  it("abre la galería filtrada por marca y aplica una plantilla a un clic (adaptada y sin hueco de foto)", async () => {
    const onCapas = renderPanel([]);

    fireEvent.click(screen.getByRole("button", { name: "Plantillas" }));
    expect(await screen.findByRole("dialog", { name: "Plantillas" })).toBeInTheDocument();
    expect(apiMod.api.plantillasDiseno).toHaveBeenCalledWith(
      { marca: "unotv" },
      expect.anything(),
    );

    fireEvent.click(await screen.findByTitle("Cargar «Placa»"));

    await waitFor(() => expect(onCapas).toHaveBeenCalled());
    const capas = onCapas.mock.calls.at(-1)![0] as Capa[];
    // El hueco de foto NO viaja al overlay (el video hace de foto); el titular sí, adaptado.
    expect(capas).toHaveLength(1);
    expect(capas[0].tipo).toBe("texto");
    // La galería se cierra tras aplicar.
    expect(screen.queryByRole("dialog", { name: "Plantillas" })).not.toBeInTheDocument();
  });

  it("guarda el overlay como PlantillaDiseno de la marca (con hueco de foto oculto)", async () => {
    const render_ = vi
      .spyOn(apiMod.api, "imagenRender")
      .mockResolvedValue({ id: "media/mini.png", url: "/api/media/mini.png" });
    const crear = vi
      .spyOn(apiMod.api, "crearPlantillaDiseno")
      .mockResolvedValue({ plantilla: plantilla() });

    renderPanel([nuevaCapaTexto({ x: 80, y: 1500, w: 920, h: 160, z: 5, texto: "Rótulo" })]);

    fireEvent.click(screen.getByRole("button", { name: /Guardar como plantilla/ }));
    const input = await screen.findByPlaceholderText("Nombre de la plantilla");
    fireEvent.change(input, { target: { value: "Lower third" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(crear).toHaveBeenCalled());
    expect(render_).toHaveBeenCalled();
    const cuerpo = crear.mock.calls[0][0];
    expect(cuerpo.marca).toBe("unotv");
    expect(cuerpo.nombre).toBe("Lower third");
    expect(cuerpo.tipo).toBe("foto");
    expect(cuerpo.miniatura).toBe("media/mini.png");
    const doc = cuerpo.documento as Documento;
    // El documento persistido lleva el hueco de foto OCULTO que exige el servidor + la capa real.
    const hueco = doc.capas.find((c) => c.tipo === "imagen" && (c as CapaImagen).es_foto) as CapaImagen;
    expect(hueco).toBeDefined();
    expect(hueco.visible).toBe(false);
    expect(doc.capas.some((c) => c.tipo === "texto")).toBe(true);
  });

  it("con el overlay vacío no abre el diálogo de guardar", () => {
    renderPanel([]);
    fireEvent.click(screen.getByRole("button", { name: /Guardar como plantilla/ }));
    expect(screen.queryByPlaceholderText("Nombre de la plantilla")).not.toBeInTheDocument();
  });
});

describe("documentoOverlay · zonas seguras del preset", () => {
  it("usa safe_top y safe_bottom del preset en lugar de forzar cero", () => {
    const doc = docVideo(); // preset "9:16"
    const preset = PRESETS_FORMATO_VIDEO["9:16"];
    const resultado = documentoOverlay(doc, "unotv", []);
    expect(resultado.formato.safe_top).toBe(preset.safe_top);
    expect(resultado.formato.safe_bottom).toBe(preset.safe_bottom);
  });

  it("aplica el preset correcto para cada aspecto", () => {
    for (const aspecto of ["9:16", "1:1", "16:9"] as const) {
      const doc: ComposicionVideo = { ...docVideo(), formato: { ...docVideo().formato, preset: aspecto } };
      const preset = PRESETS_FORMATO_VIDEO[aspecto];
      const resultado = documentoOverlay(doc, "unotv", []);
      expect(resultado.formato.safe_top).toBe(preset.safe_top);
      expect(resultado.formato.safe_bottom).toBe(preset.safe_bottom);
    }
  });
});

describe("FondoVideo · recorte temporal", () => {
  it("salta al recorte_in_ms del clip base al cargar los metadatos", () => {
    const doc = docVideoConClip(2000); // recorte_in_ms = 2 000 ms
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PanelOverlay doc={doc} marca="unotv" capas={[]} onCapas={vi.fn()} videoBaseUrl="videos/x.mp4" />
      </QueryClientProvider>,
    );
    const video = document.querySelector("video") as HTMLVideoElement;
    expect(video).not.toBeNull();
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(2); // 2 000 ms / 1 000 = 2 s
  });

  it("no modifica currentTime cuando recorte_in_ms es 0", () => {
    const doc = docVideoConClip(0); // sin recorte
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={client}>
        <PanelOverlay doc={doc} marca="unotv" capas={[]} onCapas={vi.fn()} videoBaseUrl="videos/x.mp4" />
      </QueryClientProvider>,
    );
    const video = document.querySelector("video") as HTMLVideoElement;
    expect(video).not.toBeNull();
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(0);
  });
});
