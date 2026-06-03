// Panel de IA dentro del editor (absorbe lo que aportaba el "Estudio"): generar una imagen desde
// un prompt y traerla al lienzo como capa, o expandir/retocar la capa-imagen seleccionada. Reusa
// los jobs de IA existentes (`/api/imagenes/*`) y el sondeo `useGeneracion`.

import { Loader2, Maximize2, Sparkles, Wand2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { MarcaIA } from "@/components/comunes/MarcaIA";
import { useGeneracion } from "@/hooks/use-generacion";
import { api } from "@/lib/api";
import type { FormatoImagen } from "@/types";

import type { Capa, CapaImagen } from "./documento";
import { nuevaCapaImagen } from "./documento";
import { useEditor, useStoreEditor } from "./usarEditor";

type TipoTrabajo = "generar" | "expandir" | "retocar" | "revisar";

export function PanelIA({ marca, formato }: { marca: string; formato: string }) {
  const store = useStoreEditor();
  const capaSel = useEditor((s) => s.documento.capas.find((c) => c.id === s.seleccion) ?? null);
  const imagenSel = capaSel?.tipo === "imagen" ? (capaSel as CapaImagen) : null;

  const [prompt, setPrompt] = useState("");
  const [instruccion, setInstruccion] = useState("");
  const gen = useGeneracion();
  const [trabajo, setTrabajo] = useState<{ tipo: TipoTrabajo; capaId?: string } | null>(null);
  const aplicado = useRef<string | null>(null);

  const fmt = formato as FormatoImagen;

  // Aplica el resultado del job al terminar (una sola vez por id).
  useEffect(() => {
    const g = gen.generacion;
    if (!g || aplicado.current === g.id) return;
    if (g.estado === "error") {
      aplicado.current = g.id;
      toast.error("La IA no pudo completar el trabajo.");
      gen.limpiar();
      setTrabajo(null);
      return;
    }
    if (g.estado !== "completado") return;
    aplicado.current = g.id;
    const objeto = g.resultado?.id;
    const st = store.getState();
    if (trabajo?.tipo === "generar" && objeto) {
      const f = st.documento.formato;
      st.agregar(nuevaCapaImagen(objeto, { x: 0, y: 0, w: f.w, h: f.h, z: 0 }));
      st.seleccionar(st.documento.capas[st.documento.capas.length - 1]?.id ?? null);
      toast.success("Imagen generada e insertada como capa.");
    } else if ((trabajo?.tipo === "expandir" || trabajo?.tipo === "retocar") && objeto && trabajo.capaId) {
      st.actualizar(trabajo.capaId, { objeto } as Partial<Capa>);
      toast.success(trabajo.tipo === "expandir" ? "Imagen expandida." : "Imagen retocada.");
    } else if (trabajo?.tipo === "revisar") {
      // El checklist se muestra en vivo desde `gen.generacion.salida`; no hay nada que aplicar.
    }
    if (trabajo?.tipo !== "revisar") {
      gen.limpiar();
      setTrabajo(null);
    }
  }, [gen, trabajo, store]);

  const lanzar = async (tipo: TipoTrabajo) => {
    if (gen.ejecutando) return;
    aplicado.current = null;
    try {
      if (tipo === "generar") {
        if (!prompt.trim()) return;
        const r = await api.imagenesGenerar({ prompt: prompt.trim(), marca: marca || undefined, formato: fmt, variantes: 1 });
        setTrabajo({ tipo });
        gen.iniciar(r.generaciones[0]);
      } else if (tipo === "expandir" && imagenSel?.objeto) {
        const r = await api.imagenesExpandir({ imagen: imagenSel.objeto, formato: fmt, marca: marca || undefined });
        setTrabajo({ tipo, capaId: imagenSel.id });
        gen.iniciar(r.generacion);
      } else if (tipo === "retocar" && imagenSel?.objeto) {
        if (!instruccion.trim()) return;
        const r = await api.imagenesRetocar({ imagen: imagenSel.objeto, instruccion: instruccion.trim() });
        setTrabajo({ tipo, capaId: imagenSel.id });
        gen.iniciar(r.generacion);
      } else if (tipo === "revisar" && imagenSel?.objeto) {
        const r = await api.imagenesRevisar({ imagen: imagenSel.objeto, marca: marca || undefined });
        setTrabajo({ tipo });
        gen.iniciar(r.generacion);
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "No se pudo lanzar la IA (¿proveedor configurado?).");
    }
  };

  const ocupado = gen.ejecutando;

  return (
    <div className="flex flex-col gap-2 p-3">
      <div className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        <Sparkles className="h-3.5 w-3.5" /> IA
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Describe la imagen a generar…"
        className="min-h-[56px] rounded border border-input bg-background p-1.5 text-sm"
      />
      <Button size="sm" disabled={ocupado || !prompt.trim()} onClick={() => lanzar("generar")}>
        {ocupado && trabajo?.tipo === "generar" ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <MarcaIA costo className="mr-1" />}
        Generar imagen
      </Button>

      <div className="mt-1 border-t border-border pt-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        Sobre la imagen seleccionada
      </div>
      {!imagenSel && <p className="text-xs text-muted-foreground">Selecciona una capa de imagen.</p>}
      {imagenSel && (
        <>
          <Button variant="outline" size="sm" disabled={ocupado} onClick={() => lanzar("expandir")}>
            <Maximize2 className="mr-1 h-4 w-4" /> Expandir (outpainting)
          </Button>
          <textarea
            value={instruccion}
            onChange={(e) => setInstruccion(e.target.value)}
            placeholder="Retoque: «oscurece el cielo»…"
            className="min-h-[44px] rounded border border-input bg-background p-1.5 text-sm"
          />
          <Button variant="outline" size="sm" disabled={ocupado || !instruccion.trim()} onClick={() => lanzar("retocar")}>
            <Wand2 className="mr-1 h-4 w-4" /> Retocar
          </Button>
          <Button variant="ghost" size="sm" disabled={ocupado} onClick={() => lanzar("revisar")}>
            Revisar (legal/editorial)
          </Button>
        </>
      )}

      {ocupado && (
        <Button variant="ghost" size="sm" onClick={() => gen.cancelar()}>
          <X className="mr-1 h-4 w-4" /> Cancelar
        </Button>
      )}
      {trabajo?.tipo === "revisar" && gen.generacion?.salida && (
        <pre className="max-h-40 overflow-auto whitespace-pre-wrap rounded border border-border bg-muted/40 p-2 text-[11px]">
          {gen.generacion.salida}
        </pre>
      )}
    </div>
  );
}
