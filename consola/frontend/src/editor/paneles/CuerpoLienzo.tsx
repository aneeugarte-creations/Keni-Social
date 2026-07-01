// Inspector sin capa seleccionada: edita el LIENZO (tamaño/aspect ratio) y el FONDO del documento.

import { adaptarDocumento } from "../adaptar";
import { ColorControl } from "../ColorControl";
import { PRESETS_FORMATO, mismoFormato } from "../formatos";
import { Seccion } from "../Seccion";
import { useEditor, useStoreEditor } from "../usarEditor";

import { Campo, CamposDegradado, Num } from "./Campos";
import { COLOR_TRANSPARENTE, alfaHex } from "./lib";

export function CuerpoLienzo() {
  const store = useStoreEditor();
  const fondo = useEditor((s) => s.documento.fondo);
  const formato = useEditor((s) => s.documento.formato);

  const setFondo = (f: typeof fondo) => store.getState().setFondo(f);
  // Ajuste MANUAL del lienzo (campos de tamaño/márgenes): cambia el formato tal cual, sin recolocar
  // capas (retoque fino en vivo mientras se teclea).
  const setFmt = (f: typeof formato) => store.getState().setFormato(f);
  // Elegir un PRESET REENCUADRA el contenido a las proporciones del destino (reescala y recoloca las
  // capas), igual que «Adaptar a…» de la barra: aplicar el preset crudo dejaba las capas descolocadas
  // o estiradas al cambiar w/h. Un clic discreto, así que reencuadrar de golpe es lo esperado.
  const aplicarPreset = (f: typeof formato) =>
    store.getState().cargar(adaptarDocumento(store.getState().documento, f));
  const PRESETS = PRESETS_FORMATO;
  const activo = (f: typeof formato) => mismoFormato(f, formato);
  const esTransparente = fondo.tipo === "color" && alfaHex(fondo.color) === 0;

  return (
    <div className="flex flex-col gap-3 p-3">
      <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Lienzo</div>

      {/* PRINCIPAL: Fondo → Tipo + (control directo según tipo). La opción "Transparente" vive en
          el mismo select (un color de alfa 0 = #00000000: el render produce PNG con alfa real y el
          editor muestra el tablero de ajedrez a través del lienzo). */}
      <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Fondo</div>
      <Campo etiqueta="Tipo">
        <select
          value={esTransparente ? "transparente" : fondo.tipo}
          onChange={(e) => {
            const tipo = e.target.value;
            if (tipo === "transparente") setFondo({ tipo: "color", color: COLOR_TRANSPARENTE });
            else if (tipo === "color")
              setFondo({ tipo: "color", color: esTransparente ? "#111315" : fondo.color || "#111315" });
            else if (tipo === "degradado")
              setFondo({ tipo: "degradado", degradado: fondo.degradado || { desde: "#0a3d62", hasta: "#111315", angulo: 180 } });
            else if (tipo === "imagen")
              setFondo({ tipo: "imagen", imagen: fondo.imagen || { media_id: "", ajuste: "cover" } });
          }}
          className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
        >
          <option value="color">Color</option>
          <option value="degradado">Degradado</option>
          <option value="imagen">Imagen</option>
          <option value="transparente">Transparente</option>
        </select>
      </Campo>
      {esTransparente && (
        <p className="text-[11px] text-muted-foreground">
          Fondo transparente: la pieza exportada llevará canal alfa (sin fondo).
        </p>
      )}
      {fondo.tipo === "color" && !esTransparente && (
        <Campo etiqueta="Color">
          <ColorControl valor={fondo.color || "#111315"} onChange={(c) => setFondo({ tipo: "color", color: c })} />
        </Campo>
      )}

      {/* MÁS: presets de formato + tamaño del lienzo. */}
      <Seccion titulo="Más">
        <div className="flex flex-wrap gap-1">
          {PRESETS.map((p) => (
            <button
              key={p.etiqueta}
              onClick={() => aplicarPreset(p.f)}
              className={`rounded border px-2 py-1 text-xs ${activo(p.f) ? "border-primary bg-accent" : "border-input hover:bg-accent/50"}`}
            >
              {p.etiqueta}
            </button>
          ))}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <Campo etiqueta="Ancho"><Num valor={formato.w} onChange={(v) => setFmt({ ...formato, w: Math.max(16, Math.round(v)) })} /></Campo>
          <Campo etiqueta="Alto"><Num valor={formato.h} onChange={(v) => setFmt({ ...formato, h: Math.max(16, Math.round(v)) })} /></Campo>
        </div>
      </Seccion>

      {/* AVANZADO: márgenes (encuadre) + degradado de fondo + fondo por imagen. */}
      <Seccion titulo="Avanzado">
        {/* MÁRGENES (encuadre): se dibujan como guías en el lienzo y el imán hace snap a ellos. Cada
            lado se acota a >=0 y < su dimensión. safe_left/right son aditivos (formatos sin ellos = 0). */}
        <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Márgenes</div>
        <div className="grid grid-cols-2 gap-2">
          <Campo etiqueta="Arriba">
            <Num valor={formato.safe_top} onChange={(v) => setFmt({ ...formato, safe_top: Math.max(0, Math.min(formato.h - 1, Math.round(v))) })} />
          </Campo>
          <Campo etiqueta="Abajo">
            <Num valor={formato.safe_bottom} onChange={(v) => setFmt({ ...formato, safe_bottom: Math.max(0, Math.min(formato.h - 1, Math.round(v))) })} />
          </Campo>
          <Campo etiqueta="Izquierda">
            <Num valor={formato.safe_left ?? 0} onChange={(v) => setFmt({ ...formato, safe_left: Math.max(0, Math.min(formato.w - 1, Math.round(v))) })} />
          </Campo>
          <Campo etiqueta="Derecha">
            <Num valor={formato.safe_right ?? 0} onChange={(v) => setFmt({ ...formato, safe_right: Math.max(0, Math.min(formato.w - 1, Math.round(v))) })} />
          </Campo>
        </div>
        {fondo.tipo === "degradado" && fondo.degradado && (
          <>
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Degradado de fondo</div>
            <CamposDegradado
              deg={fondo.degradado}
              onChange={(d) => setFondo({ tipo: "degradado", degradado: d })}
            />
          </>
        )}
        {fondo.tipo === "imagen" && (
          <>
            <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">Fondo por imagen</div>
            <Campo etiqueta="Media ID">
              <input
                type="text"
                value={fondo.imagen?.media_id ?? ""}
                placeholder="id de media"
                onChange={(e) =>
                  setFondo({ tipo: "imagen", imagen: { media_id: e.target.value.trim(), ajuste: fondo.imagen?.ajuste ?? "cover" } })
                }
                className="w-40 rounded border border-input bg-background px-1.5 py-0.5 text-right text-xs"
              />
            </Campo>
            <Campo etiqueta="Ajuste">
              <select
                value={fondo.imagen?.ajuste ?? "cover"}
                onChange={(e) =>
                  setFondo({ tipo: "imagen", imagen: { media_id: fondo.imagen?.media_id ?? "", ajuste: e.target.value as "cover" | "contain" } })
                }
                className="rounded border border-input bg-background px-1.5 py-0.5 text-xs"
              >
                <option value="cover">Cubrir</option>
                <option value="contain">Contener</option>
              </select>
            </Campo>
          </>
        )}
      </Seccion>
    </div>
  );
}
