// Fragmento del cliente API: dominio «insumos». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  EventoRota,
  Generacion,
  InsumoItem,
  InsumoLote,
  RespuestaDiasInsumos,
  RespuestaInsumos,
} from "@/types";

export const apiInsumos = {
  // --- Insumos del día (cajones) ---
  // El equipo vuelca material diario en 4 cajones; Haiku lo parsea y produce
  // ítems listos para llevar al tablero. Contrato: docs/maquina-contenido/01-insumos-del-dia.md.
  insumos: {
    /** Lista los 4 cajones con sus lotes e ítems para `fecha` (def: hoy en el servidor).
     *
     * `soloFrescos=true` activa `solo_frescos=1` en la query: los ítems caducados se ocultan
     * (no se borran). Útil para UnoTV donde publicar noticias de ayer es perjudicial.
     */
    listar: (fecha?: string, signal?: AbortSignal, soloFrescos?: boolean, marca?: string) =>
      peticion<RespuestaInsumos>(
        `/insumos${query({ fecha, ...(soloFrescos ? { solo_frescos: "1" } : {}), ...(marca ? { marca } : {}) })}`,
        { signal },
      ),

    /** Días con insumos registrados (orden: fecha desc). Para el selector de historial. */
    dias: (signal?: AbortSignal) =>
      peticion<RespuestaDiasInsumos>("/insumos/dias", { signal }),

    /**
     * Aporta material a un cajón. ASÍNCRONO: crea el lote en estado `parseando` y ENCOLA un
     * job (Haiku) que el WORKER ejecuta (el back no tiene `claude`). Devuelve el lote +
     * la `generacion` para sondear; los ítems aparecen al recargar el cajón cuando el lote
     * pasa a `listo`. Acepta texto pegado y/o archivo.
     */
    aportar: (form: FormData) =>
      peticion<{ lote: InsumoLote; generacion: Generacion | null }>("/insumos/aportar", {
        metodo: "POST",
        form,
      }),

    /** Detalle de un lote con sus ítems. */
    lote: (id: string, signal?: AbortSignal) =>
      peticion<{ lote: InsumoLote; items: InsumoItem[] }>(
        `/insumos/lote/${encodeURIComponent(id)}`,
        { signal },
      ),

    /** Edición parcial de un ítem (título, resumen, marca, línea, hora, lugar, etc.). */
    editarItem: (
      id: string,
      campos: Partial<Pick<InsumoItem, "titulo" | "resumen" | "marca" | "linea" | "hora" | "lugar" | "estado_material" | "tipo">>,
    ) =>
      peticion<{ item: InsumoItem }>(`/insumos/item/${encodeURIComponent(id)}`, {
        metodo: "PATCH",
        json: campos,
        muestrear: false,
      }),

    /**
     * Lleva un ítem al tablero: crea contenido con `origen="insumo"` y marca el ítem
     * como `usado`. Acepta `redes` y `generar` (lanza copy si `true` y hay marca).
     */
    usarItem: (id: string, body: { redes?: string[]; generar?: boolean }) =>
      peticion<{ item: InsumoItem; contenido_id: string }>(
        `/insumos/item/${encodeURIComponent(id)}/usar`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /**
     * Convierte un ítem del cajón `eventos_claro` (tipo='evento') en un evento de la
     * rota (`/api/rota/eventos`): mapea titulo/fecha/hora/resumen→nota y marca el ítem
     * como usado guardando el id del evento en `contenido_id`. Devuelve el evento creado.
     */
    crearEvento: (
      id: string,
      body: { tipo_cobertura?: string; prioridad?: string } = {},
    ) =>
      peticion<{ item: InsumoItem; evento: EventoRota; evento_id: string }>(
        `/insumos/item/${encodeURIComponent(id)}/crear-evento`,
        { metodo: "POST", json: body, muestrear: false },
      ),

    /** Borra un lote y todos sus ítems. */
    borrarLote: (id: string) =>
      peticion<{ ok: boolean }>(`/insumos/lote/${encodeURIComponent(id)}`, {
        metodo: "DELETE",
        muestrear: false,
      }),
  },

};
