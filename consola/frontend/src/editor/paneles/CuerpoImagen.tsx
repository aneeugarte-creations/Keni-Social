// Inspector · capa de IMAGEN: hueco de foto, forma/ajuste, reencuadre, filtros, duotono, sombra,
// recorte por % y conversión a forma.

import { Crop as CropIcon, FlipHorizontal2, FlipVertical2, Loader2, Scissors } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { api, mensajeError } from "@/lib/api";

import { ColorControl } from "../ColorControl";

import type { Capa, CapaImagen, Filtros, Forma } from "../documento";
import { CATALOGO_FORMAS, ETIQUETA_FORMA } from "../documento";
import { Seccion } from "../Seccion";
import { useStoreEditor } from "../usarEditor";

import { Campo, CamposSombra, Num, RadioEsquinas } from "./Campos";
import type { PropsCuerpoCapa } from "./tipos";

export function CuerpoImagen({ capa, set, onRecortar }: PropsCuerpoCapa<CapaImagen> & { onRecortar?: () => void }) {
  const store = useStoreEditor();

  // «Quitar fondo»: manda el objeto de la capa al servidor (rembg), que devuelve un PNG con el
  // fondo transparente como objeto NUEVO; la capa cambia su `objeto` al recorte (se puede deshacer).
  const [quitandoFondo, setQuitandoFondo] = useState(false);
  const quitarFondo = async () => {
    if (!capa.objeto || quitandoFondo) return;
    setQuitandoFondo(true);
    try {
      const res = await api.imagenQuitarFondo(capa.objeto);
      store.getState().actualizar(capa.id, { objeto: res.id } as Partial<Capa>);
      toast.success("Fondo quitado.");
    } catch (e) {
      toast.error(mensajeError(e));
    } finally {
      setQuitandoFondo(false);
    }
  };

  // Edita un filtro de imagen fusionando con el resto (neutros por defecto). Si el resultado es
  // neutro (brillo=contraste=saturacion=1, desenfoque=0) colapsa a `null`, igual que el back.
  const setFiltro = (k: "brillo" | "contraste" | "saturacion" | "desenfoque", v: number) => {
    const next = { brillo: 1, contraste: 1, saturacion: 1, desenfoque: 0, ...capa.filtros, [k]: v };
    const neutro = next.brillo === 1 && next.contraste === 1 && next.saturacion === 1 && next.desenfoque === 0;
    // Si hay duotono no colapsamos a null aunque brillo/contraste sean neutros (el duotono es un
    // filtro más). El back hace lo mismo (`_filtros` cuenta el duotono como no-neutro).
    set({ filtros: neutro && !next.duotono ? null : next } as Partial<Capa>);
  };
  const fil = capa.filtros ?? { brillo: 1, contraste: 1, saturacion: 1, desenfoque: 0 };

  return (
    <>
      {/* IMAGEN · PRINCIPAL: hueco de foto, forma y ajuste. */}
      <div className="flex flex-col gap-2 border-t border-border pt-3">
        {/* Hueco de foto: la capa donde entra una foto de la pieza. Una plantilla puede tener
            VARIOS (collage de 2..12); mínimo uno. Marcarlo lo deja bloqueado; "Quitar" lo libera. */}
        <Campo etiqueta="Hueco de foto">
          {capa.es_foto ? (
            <div className="flex items-center gap-1.5">
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-600 dark:text-emerald-400">
                Sí · bloqueado
              </span>
              <button
                type="button"
                onClick={() =>
                  store.getState().actualizar(capa.id, { es_foto: false, bloqueada: false } as Partial<Capa>)
                }
                className="rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
              >
                Quitar
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => store.getState().marcarHuecoFoto(capa.id)}
              className="rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
            >
              Marcar como hueco
            </button>
          )}
        </Campo>
        {capa.es_foto && (
          <p className="text-[11px] text-muted-foreground">Hueco de foto. Marca varios para un collage.</p>
        )}
        <Campo etiqueta="Forma">
          <select
            value={capa.forma ?? "rect"}
            onChange={(e) => set({ forma: e.target.value as Forma } as Partial<Capa>)}
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            {CATALOGO_FORMAS.map((f) => (
              <option key={f} value={f}>{ETIQUETA_FORMA[f]}</option>
            ))}
          </select>
        </Campo>
        <Campo etiqueta="Ajuste">
          <select
            value={capa.ajuste}
            onChange={(e) => set({ ajuste: e.target.value as CapaImagen["ajuste"] } as Partial<Capa>)}
            className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
          >
            <option value="cover">Cubrir</option>
            <option value="contain">Contener</option>
          </select>
        </Campo>
        {/* VOLTEO (flip): espejo horizontal/vertical alrededor del centro de la caja. */}
        <Campo etiqueta="Voltear">
          <div className="flex items-center gap-1">
            <button
              type="button"
              aria-label="Voltear horizontal"
              aria-pressed={!!capa.flip_h}
              onClick={() => set({ flip_h: !capa.flip_h } as Partial<Capa>)}
              className={`rounded border border-input p-1 hover:bg-accent ${capa.flip_h ? "bg-accent" : "bg-background"}`}
            >
              <FlipHorizontal2 className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              aria-label="Voltear vertical"
              aria-pressed={!!capa.flip_v}
              onClick={() => set({ flip_v: !capa.flip_v } as Partial<Capa>)}
              className={`rounded border border-input p-1 hover:bg-accent ${capa.flip_v ? "bg-accent" : "bg-background"}`}
            >
              <FlipVertical2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </Campo>
        {/* QUITAR FONDO: recorta el sujeto y deja el fondo transparente (server-side). Solo tiene
            sentido cuando la capa YA tiene una foto real cargada (`objeto`), no en un hueco vacío. */}
        {capa.objeto && (
          <Campo etiqueta="Fondo">
            <button
              type="button"
              onClick={quitarFondo}
              disabled={quitandoFondo}
              title="Recorta el sujeto y deja el fondo transparente"
              className="flex items-center gap-1 rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent disabled:opacity-60"
            >
              {quitandoFondo ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Scissors className="h-3.5 w-3.5" />
              )}
              {quitandoFondo ? "Quitando…" : "Quitar fondo"}
            </button>
          </Campo>
        )}
      </div>

      {/* IMAGEN · MÁS: reencuadre rápido (recorte visual + zoom). */}
      <Seccion titulo="Más">
        {onRecortar && (
          <button
            type="button"
            onClick={onRecortar}
            className="flex items-center gap-1 self-start rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
            title="Recortar visualmente con tiradores"
          >
            <CropIcon className="h-3.5 w-3.5" /> Recortar
          </button>
        )}
        <Campo etiqueta="Zoom (reencuadre)">
          <input
            type="range"
            min={1}
            max={6}
            step={0.05}
            value={capa.zoom ?? 1}
            onChange={(e) => set({ zoom: Number(e.target.value) } as Partial<Capa>)}
            className="w-24"
          />
        </Campo>
      </Seccion>

      {/* IMAGEN · AVANZADO: esquinas, filtros, duotono, sombra, recorte por % y conversión. */}
      <Seccion titulo="Avanzado">
        {/* "Esquinas" (radio uniforme o por esquina) solo aplica al rectángulo. */}
        {(capa.forma ?? "rect") === "rect" && (
          <RadioEsquinas
            radio={capa.radio ?? 0}
            radios={capa.radios}
            onChange={(cambios) => set(cambios as Partial<Capa>)}
          />
        )}
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Filtros</div>
        {/* Presets de un clic: fijan brillo/contraste/saturación/desenfoque de golpe (reusan el
            esquema `filtros`, sin campos nuevos). "B&N" desatura del todo (saturación 0 = gris en
            previa y export); "Quitar" vuelve a neutro. El duotono se conserva si estaba activo. */}
        <div className="flex flex-wrap gap-1">
          {(() => {
            const presets: { etiqueta: string; cambios: Filtros | null }[] = [
              { etiqueta: "B&N", cambios: { brillo: 1.05, contraste: 1.1, saturacion: 0, desenfoque: 0 } },
              { etiqueta: "Cálido", cambios: { brillo: 1.05, contraste: 1.05, saturacion: 1.35, desenfoque: 0 } },
              { etiqueta: "Dramático", cambios: { brillo: 0.9, contraste: 1.5, saturacion: 1.15, desenfoque: 0 } },
              { etiqueta: "Desaturado marca", cambios: { brillo: 1, contraste: 1.08, saturacion: 0.55, desenfoque: 0 } },
              { etiqueta: "Quitar", cambios: null },
            ];
            return presets.map((p) => (
              <button
                key={p.etiqueta}
                type="button"
                onClick={() => {
                  if (!p.cambios) {
                    // Conserva el duotono (es un filtro aparte); si no hay, colapsa a null.
                    set({ filtros: capa.filtros?.duotono ? { brillo: 1, contraste: 1, saturacion: 1, desenfoque: 0, duotono: capa.filtros.duotono } : null } as Partial<Capa>);
                    return;
                  }
                  set({ filtros: { ...p.cambios, duotono: capa.filtros?.duotono ?? null } } as Partial<Capa>);
                }}
                className="rounded border border-input bg-background px-1.5 py-0.5 text-[11px] hover:bg-accent"
              >
                {p.etiqueta}
              </button>
            ));
          })()}
        </div>
        <Campo etiqueta="Brillo">
          <input type="range" min={0.2} max={1.8} step={0.05} value={fil.brillo ?? 1} onChange={(e) => setFiltro("brillo", Number(e.target.value))} className="w-24" />
        </Campo>
        <Campo etiqueta="Contraste">
          <input type="range" min={0.2} max={1.8} step={0.05} value={fil.contraste ?? 1} onChange={(e) => setFiltro("contraste", Number(e.target.value))} className="w-24" />
        </Campo>
        <Campo etiqueta="Saturación">
          <input type="range" min={0} max={2} step={0.05} value={fil.saturacion ?? 1} onChange={(e) => setFiltro("saturacion", Number(e.target.value))} className="w-24" />
        </Campo>
        <Campo etiqueta="Desenfoque">
          <input type="range" min={0} max={20} step={1} value={fil.desenfoque ?? 0} onChange={(e) => setFiltro("desenfoque", Number(e.target.value))} className="w-24" />
        </Campo>
        <button onClick={() => set({ filtros: null } as Partial<Capa>)} className="self-start text-xs text-muted-foreground underline">
          Quitar filtros
        </button>
        {/* DUOTONO: tinte de marca por luminancia (sombras->color1, luces->color2). */}
        <Campo etiqueta="Duotono">
          <input
            type="checkbox"
            checked={!!fil.duotono}
            onChange={(e) =>
              set({
                filtros: {
                  brillo: fil.brillo ?? 1,
                  contraste: fil.contraste ?? 1,
                  saturacion: fil.saturacion ?? 1,
                  desenfoque: fil.desenfoque ?? 0,
                  duotono: e.target.checked ? { sombra: "#111315", luz: "#E30613" } : null,
                },
              } as Partial<Capa>)
            }
          />
        </Campo>
        {fil.duotono && (
          <div className="grid grid-cols-2 gap-2 pl-2">
            <Campo etiqueta="Sombra">
              <ColorControl
                valor={fil.duotono.sombra}
                onChange={(c) => set({ filtros: { ...fil, duotono: { ...fil.duotono!, sombra: c } } } as Partial<Capa>)}
              />
            </Campo>
            <Campo etiqueta="Luz">
              <ColorControl
                valor={fil.duotono.luz}
                onChange={(c) => set({ filtros: { ...fil, duotono: { ...fil.duotono!, luz: c } } } as Partial<Capa>)}
              />
            </Campo>
          </div>
        )}
        <Campo etiqueta="Sombra">
          <input
            type="checkbox"
            checked={!!capa.sombra}
            onChange={(e) => set({ sombra: e.target.checked ? { dx: 0, dy: 12, color: "#000000", desenfoque: 24, opacidad: 0.5 } : null } as Partial<Capa>)}
          />
        </Campo>
        {capa.sombra && (
          <CamposSombra sombra={capa.sombra} onChange={(s) => set({ sombra: s } as Partial<Capa>)} />
        )}
        {/* RECORTE (crop) no destructivo de la fuente: 4 campos en % (Izq/Arriba/Ancho/Alto). El
            editor visual (botón "Recortar") vive en "Más"; aquí van los campos numéricos finos. */}
        {(() => {
          const crop = capa.crop;
          const pct = (v: number) => Math.round(v * 1000) / 10;
          const setCrop = (k: "cx" | "cy" | "cw" | "ch", v: number) => {
            const actual = crop ?? { cx: 0, cy: 0, cw: 1, ch: 1 };
            const f = Math.max(0, Math.min(1, v / 100));
            set({ crop: { ...actual, [k]: f } } as Partial<Capa>);
          };
          return (
            <>
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Recorte</div>
              <div className="grid grid-cols-2 gap-2">
                <Campo etiqueta="Izq. %"><Num valor={pct(crop?.cx ?? 0)} onChange={(v) => setCrop("cx", v)} /></Campo>
                <Campo etiqueta="Arriba %"><Num valor={pct(crop?.cy ?? 0)} onChange={(v) => setCrop("cy", v)} /></Campo>
                <Campo etiqueta="Ancho %"><Num valor={pct(crop?.cw ?? 1)} onChange={(v) => setCrop("cw", v)} /></Campo>
                <Campo etiqueta="Alto %"><Num valor={pct(crop?.ch ?? 1)} onChange={(v) => setCrop("ch", v)} /></Campo>
              </div>
              {crop && (
                <button
                  type="button"
                  onClick={() => set({ crop: undefined } as Partial<Capa>)}
                  className="self-start text-xs text-muted-foreground underline"
                >
                  Quitar recorte
                </button>
              )}
            </>
          );
        })()}
        {/* Convertir la foto en una FORMA (marco) vacía, conservando su silueta. */}
        {!capa.es_foto && (
          <button
            type="button"
            onClick={() => store.getState().convertirEnMarco(capa.id)}
            className="self-start rounded border border-input bg-background px-1.5 py-0.5 text-xs hover:bg-accent"
          >
            Convertir en forma
          </button>
        )}
      </Seccion>
    </>
  );
}
