// Página del Editor profesional — WORKSPACE multi-marca (Frente A + B).
//
// Cada PESTAÑA es un documento independiente (marca + formato) con su PROPIO store Zustand e
// historial, así editar la plantilla de UnoTV no toca la de Claro Sports y no hay que cerrar una
// para abrir otra. Los stores persisten en un ref por id de pestaña: cambiar de pestaña conserva
// las ediciones (no recarga la plantilla).

import { useMutation, useQuery } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { SelectorMarca } from "@/components/comunes/SelectorMarca";
import { Button } from "@/components/ui/button";
import { EditorDocumento } from "@/editor/EditorDocumento";
import { documentoVacio, type Documento } from "@/editor/documento";
import { crearStoreEditor, type StoreEditor } from "@/editor/store";
import { api } from "@/lib/api";

const DIMS: Record<string, Documento["formato"]> = {
  vertical: { w: 1080, h: 1920, safe_top: 220, safe_bottom: 420 },
  feed: { w: 1080, h: 1350, safe_top: 60, safe_bottom: 96 },
  cuadrado: { w: 1080, h: 1080, safe_top: 60, safe_bottom: 96 },
  horizontal: { w: 1600, h: 900, safe_top: 56, safe_bottom: 72 },
};
const FORMATOS = Object.keys(DIMS);

interface Pestana {
  id: string;
  marca: string;
  formato: string;
}

let _seq = 0;

export default function EditorPro() {
  const opciones = useQuery({
    queryKey: ["publicaciones", "opciones"],
    queryFn: ({ signal }) => api.publicacionesOpciones(signal),
  });
  const marcas = opciones.data?.marcas ?? [];

  // Selectores para abrir una pestaña nueva.
  const [marcaNueva, setMarcaNueva] = useState("");
  const [formatoNuevo, setFormatoNuevo] = useState("feed");

  const [pestanas, setPestanas] = useState<Pestana[]>([]);
  const [activa, setActiva] = useState<string | null>(null);
  // Stores por pestaña (persisten entre cambios de pestaña).
  const stores = useRef<Map<string, StoreEditor>>(new Map());
  const [exportUrl, setExportUrl] = useState<string | null>(null);

  const marcaEfectiva = marcaNueva || marcas[0]?.id || "";

  const abrirPestana = async () => {
    if (!marcaEfectiva) return;
    _seq += 1;
    const id = `tab-${_seq}`;
    const store = crearStoreEditor(documentoVacio(DIMS[formatoNuevo] ?? DIMS.feed, marcaEfectiva));
    stores.current.set(id, store);
    setPestanas((p) => [...p, { id, marca: marcaEfectiva, formato: formatoNuevo }]);
    setActiva(id);
    // Carga la plantilla de la marca en el store de ESTA pestaña (una sola vez).
    try {
      const res = await api.editorPlantilla(marcaEfectiva, formatoNuevo);
      store.getState().cargar(res.documento as Documento);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo cargar la plantilla.");
    }
  };

  const cerrarPestana = (id: string) => {
    stores.current.delete(id);
    setPestanas((p) => {
      const resto = p.filter((t) => t.id !== id);
      if (activa === id) setActiva(resto.length ? resto[resto.length - 1].id : null);
      return resto;
    });
  };

  const exportar = useMutation({
    mutationFn: () => {
      const store = activa ? stores.current.get(activa) : null;
      if (!store) throw new Error("No hay pestaña activa.");
      return api.editorRender(store.getState().documento);
    },
    onSuccess: (res) => {
      setExportUrl(`/api/media/${res.id}`);
      toast.success("PNG generado.");
    },
    onError: (e: unknown) => toast.error(e instanceof Error ? e.message : "No se pudo exportar."),
  });

  const pestanaActiva = pestanas.find((t) => t.id === activa) ?? null;
  const storeActivo = activa ? stores.current.get(activa) ?? null : null;

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Barra superior: abrir pestaña (marca + formato) + export. */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
        <h1 className="mr-1 text-base font-semibold">Editor</h1>
        <SelectorMarca marcas={marcas} valor={marcaEfectiva} onCambio={setMarcaNueva} incluirTodas={false} />
        <select
          value={formatoNuevo}
          onChange={(e) => setFormatoNuevo(e.target.value)}
          className="rounded border border-input bg-background px-2 py-1.5 text-sm"
          aria-label="Formato"
        >
          {FORMATOS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <Button variant="outline" size="sm" onClick={abrirPestana} disabled={!marcaEfectiva}>
          <Plus className="mr-1 h-4 w-4" /> Abrir
        </Button>
        {exportUrl && (
          <a href={exportUrl} target="_blank" rel="noreferrer" className="ml-auto text-sm text-primary underline">
            Ver PNG exportado
          </a>
        )}
      </div>

      {/* Pestañas abiertas. */}
      {pestanas.length > 0 && (
        <div className="flex items-center gap-1 overflow-x-auto border-b border-border bg-muted/30 px-2">
          {pestanas.map((t) => {
            const nombre = marcas.find((m) => m.id === t.marca)?.nombre ?? t.marca;
            return (
              <div
                key={t.id}
                className={`flex items-center gap-1 border-b-2 px-3 py-1.5 text-sm ${
                  t.id === activa ? "border-primary font-medium" : "border-transparent text-muted-foreground"
                }`}
              >
                <button onClick={() => setActiva(t.id)}>
                  {nombre} · {t.formato}
                </button>
                <button onClick={() => cerrarPestana(t.id)} className="opacity-60 hover:opacity-100" title="Cerrar">
                  <X className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="min-h-0 flex-1">
        {pestanaActiva && storeActivo ? (
          <EditorDocumento
            key={pestanaActiva.id}
            store={storeActivo}
            marca={pestanaActiva.marca}
            onExportar={() => exportar.mutate()}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Elige una marca y un formato, y pulsa «Abrir» para empezar a editar.
          </div>
        )}
      </div>
    </div>
  );
}
