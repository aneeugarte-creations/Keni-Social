// Página del Editor profesional (Frente A): carga la plantilla de una marca como Documento de
// capas, la edita en un lienzo Konva y exporta el PNG final con re-render server-side.

import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { documentoVacio, type Documento } from "@/editor/documento";
import { crearStoreEditor } from "@/editor/store";
import { api } from "@/lib/api";

const DIMS: Record<string, Documento["formato"]> = {
  vertical: { w: 1080, h: 1920, safe_top: 220, safe_bottom: 420 },
  feed: { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 },
  cuadrado: { w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 },
  horizontal: { w: 1600, h: 900, safe_top: 56, safe_bottom: 72 },
};
const FORMATOS = Object.keys(DIMS);

export default function EditorPro() {
  const opciones = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opciones.data?.marcas ?? [];

  const [marca, setMarca] = useState("");
  const [formato, setFormato] = useState("feed");
  const [exportUrl, setExportUrl] = useState<string | null>(null);

  // Selecciona la primera marca disponible cuando llegan las opciones.
  useEffect(() => {
    const ms = opciones.data?.marcas ?? [];
    if (!marca && ms.length > 0) setMarca(ms[0].id);
  }, [marca, opciones.data]);

  // Un store por montaje de la página (en el Frente B será uno por pestaña del workspace).
  const store = useMemo(() => crearStoreEditor(documentoVacio(DIMS.feed)), []);

  // Carga la plantilla de la marca/formato elegidos como Documento de capas.
  const plantilla = useQuery({
    queryKey: ["editor-plantilla", marca, formato],
    queryFn: ({ signal }) => api.editorPlantilla(marca, formato, signal),
    enabled: !!marca,
  });

  useEffect(() => {
    if (plantilla.data?.documento) {
      store.getState().cargar(plantilla.data.documento as Documento);
    }
  }, [plantilla.data, store]);

  const exportar = useMutation({
    mutationFn: () => api.editorRender(store.getState().documento),
    onSuccess: (res) => {
      setExportUrl(`/api/media/${res.id}`);
      toast.success("PNG generado.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo exportar."),
  });

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-3">
        <h1 className="mr-2 text-lg font-semibold">Editor</h1>
        <SelectorMarca marcas={marcas} valor={marca} onCambio={setMarca} incluirTodas={false} />
        <select
          value={formato}
          onChange={(e) => setFormato(e.target.value)}
          className="rounded border border-input bg-background px-2 py-1.5 text-sm"
          aria-label="Formato"
        >
          {FORMATOS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        {plantilla.isFetching && <span className="text-xs text-muted-foreground">Cargando plantilla…</span>}
        {exportUrl && (
          <a
            href={exportUrl}
            target="_blank"
            rel="noreferrer"
            className="ml-auto text-sm text-primary underline"
          >
            Ver PNG exportado
          </a>
        )}
      </div>
      <div className="min-h-0 flex-1">
        <EditorDocumento store={store} onExportar={() => exportar.mutate()} />
      </div>
    </div>
  );
}
