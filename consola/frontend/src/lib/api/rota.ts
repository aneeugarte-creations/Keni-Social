// Fragmento del cliente API: dominio «rota». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query, queryEventos, descargar } from "./_core";
import type {
  AlcanceSerie,
  CoordinacionTurno,
  CuerpoActualizarAusenciaRota,
  CuerpoActualizarEventoRota,
  CuerpoActualizarFranjaSemana,
  CuerpoActualizarLoteTurnos,
  CuerpoActualizarProgramaRota,
  CuerpoActualizarTurnoRota,
  CuerpoAprobarRota,
  CuerpoBorrarLoteIds,
  CuerpoCopiarSemana,
  CuerpoCrearAusenciaRota,
  CuerpoCrearEventoRota,
  CuerpoCrearFranjaSemana,
  CuerpoCrearProgramaRota,
  CuerpoCrearSwap,
  CuerpoCrearTurnoRota,
  CuerpoCrearTurnosLote,
  CuerpoDecidirSwap,
  CuerpoDuplicarEventoRota,
  CuerpoDuplicarTurnoRota,
  CuerpoGuardarConfigFranjas,
  CuerpoQuitarCoordinador,
  CuerpoSetCoordinador,
  FiltrosSwaps,
  FranjaSemana,
  MisTurnosMesRota,
  MisTurnosRota,
  RespuestaActualizarLoteTurnos,
  RespuestaAusenciaRota,
  RespuestaAusenciasRota,
  RespuestaBorrarLote,
  RespuestaCargaRota,
  RespuestaCoberturaEvento,
  RespuestaCoberturaSemana,
  RespuestaConfigFranjas,
  RespuestaCoordinacionSemana,
  RespuestaCopiarSemana,
  RespuestaCrearEventoRota,
  RespuestaCrearTurnosLote,
  RespuestaEquipoRota,
  RespuestaEventoRota,
  RespuestaEventosRota,
  RespuestaFranjasSemana,
  RespuestaMensaje,
  RespuestaProgramaRota,
  RespuestaProgramasRota,
  RespuestaSwap,
  RespuestaSwaps,
  RespuestaTurnoRota,
  RotaSemana,
  TurnosMesRota,
} from "@/types";

export const apiRota = {
  // --- Rota de horarios del equipo (F4 · #144) ---
  rotaEquipo: (signal?: AbortSignal) =>
    peticion<RespuestaEquipoRota>("/rota/equipo", { signal }),
  /**
   * Equipo COMPLETO (incluye quienes no cubren, p. ej. coordinadores con
   * `cobertura=false`). Necesario para resolver candidatos a coordinador (ola "coord")
   * que pueden no estar en el equipo de rota habitual.
   */
  rotaEquipoTodos: (signal?: AbortSignal) =>
    peticion<RespuestaEquipoRota>("/rota/equipo?todos=1", { signal }),
  rotaEventos: (
    params: {
      desde?: string;
      hasta?: string;
      cambiados?: string;
      tipo_cobertura?: string | string[];
      prioridad?: string | string[];
      cambiado?: boolean | null;
      q?: string;
      /** Id canónico de marca; ausente/vacío = todas las marcas. */
      marca?: string;
    } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaEventosRota>(`/rota/eventos${queryEventos(params)}`, { signal }),
  // Crea un evento suelto o, si el cuerpo trae `dias_semana` + `repetir_hasta`, una SERIE
  // recurrente (respuesta `{eventos, serie_id, total}`). El llamante distingue por la forma.
  crearEventoRota: (cuerpo: CuerpoCrearEventoRota) =>
    peticion<RespuestaCrearEventoRota>("/rota/eventos", { metodo: "POST", json: cuerpo }),
  actualizarEventoRota: (id: string, cuerpo: CuerpoActualizarEventoRota) =>
    peticion<RespuestaEventoRota>(`/rota/eventos/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  // `alcance` (solo útil en una serie): "este" (def.) borra el evento; "siguientes" borra este
  // y los posteriores de la serie; "serie" la borra entera.
  eliminarEventoRota: (id: string, alcance?: AlcanceSerie) =>
    peticion<RespuestaMensaje & { eliminados?: number }>(
      `/rota/eventos/${encodeURIComponent(id)}${alcance ? `?alcance=${alcance}` : ""}`,
      { metodo: "DELETE" },
    ),
  duplicarEventoRota: (id: string, cuerpo: CuerpoDuplicarEventoRota = {}) =>
    peticion<RespuestaEventoRota>(`/rota/eventos/${encodeURIComponent(id)}/duplicar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  // --- Turnos (modelo nuevo: persona × día × franja, ola back3) ---
  // CRUD primario sobre los turnos. La cobertura de eventos es derivada (ver más
  // abajo). `listarTurnos` admite `?lunes=` para acotar a una semana (recomendado).
  // GRID POR MARCA: `marca` acota a la rejilla de esa marca; ausente = "Todas" (apila todas).
  listarTurnos: (params: { lunes?: string; marca?: string } = {}, signal?: AbortSignal) =>
    peticion<RotaSemana>(`/rota/turnos${query(params)}`, { signal }),
  crearTurno: (cuerpo: CuerpoCrearTurnoRota) =>
    peticion<RespuestaTurnoRota>("/rota/turnos", { metodo: "POST", json: cuerpo }),
  actualizarTurno: (id: string, cuerpo: CuerpoActualizarTurnoRota) =>
    peticion<RespuestaTurnoRota>(`/rota/turnos/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  borrarTurno: (id: string) =>
    peticion<RespuestaMensaje>(`/rota/turnos/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  crearTurnosLote: (cuerpo: CuerpoCrearTurnosLote) =>
    peticion<RespuestaCrearTurnosLote>("/rota/turnos/lote", {
      metodo: "POST",
      json: cuerpo,
    }),
  actualizarTurnosLote: (cuerpo: CuerpoActualizarLoteTurnos) =>
    peticion<RespuestaActualizarLoteTurnos>("/rota/turnos/lote", {
      metodo: "PATCH",
      json: cuerpo,
    }),
  borrarTurnosLote: (cuerpo: CuerpoBorrarLoteIds) =>
    peticion<RespuestaBorrarLote>("/rota/turnos/lote/borrar", {
      metodo: "POST",
      json: cuerpo,
    }),
  duplicarTurno: (id: string, cuerpo: CuerpoDuplicarTurnoRota = {}) =>
    peticion<RespuestaTurnoRota>(`/rota/turnos/${encodeURIComponent(id)}/duplicar`, {
      metodo: "POST",
      json: cuerpo,
    }),
  aprobarTurnos: (cuerpo: CuerpoAprobarRota) =>
    peticion<RotaSemana>("/rota/turnos/aprobar", { metodo: "POST", json: cuerpo }),
  /** Revierte la semana publicada a borrador (solo admin). */
  despublicarTurnos: (cuerpo: CuerpoAprobarRota) =>
    peticion<RotaSemana>("/rota/turnos/despublicar", { metodo: "POST", json: cuerpo }),
  misTurnos: (params: { lunes?: string; marca?: string } = {}, signal?: AbortSignal) =>
    peticion<MisTurnosRota>(`/rota/mis-turnos${query(params)}`, { signal }),
  /**
   * Calendario MENSUAL de «Mis turnos»: solo el horario propio del mes, SIN eventos ni
   * cobertura. `mes` = "AAAA-MM" (ausente = mes actual). GRID POR MARCA: `marca` acota.
   */
  misTurnosMes: (params: { mes?: string; marca?: string } = {}, signal?: AbortSignal) =>
    peticion<MisTurnosMesRota>(`/rota/mis-turnos/mes${query(params)}`, { signal }),
  /**
   * Calendario MENSUAL del EQUIPO: los turnos de TODO el equipo en el mes, sin eventos ni
   * cobertura. `mes` = "AAAA-MM" (ausente = mes actual). GRID POR MARCA: `marca` acota.
   */
  turnosMes: (params: { mes?: string; marca?: string } = {}, signal?: AbortSignal) =>
    peticion<TurnosMesRota>(`/rota/turnos/mes${query(params)}`, { signal }),
  exportarRota: (formato: "xlsx" | "csv", params: { lunes?: string; marca?: string } = {}) =>
    descargar(`/rota/export.${formato}${query(params)}`),

  // --- Cobertura DERIVADA (no persistida): eventos × turnos ---
  cobertura: (
    params: { lunes: string; marca?: string },
    signal?: AbortSignal,
  ) => peticion<RespuestaCoberturaSemana>(`/rota/cobertura${query(params)}`, { signal }),
  coberturaEvento: (eventoId: string, signal?: AbortSignal) =>
    peticion<RespuestaCoberturaEvento>(
      `/rota/cobertura/evento/${encodeURIComponent(eventoId)}`,
      { signal },
    ),

  // --- Coordinador por turno (ola "coord") ---
  // Una celda (fecha, franja_id) puede tener UN coordinador entre los usuarios con
  // `puede_coordinar=true`. La coordinación es independiente del turno de CM.
  listarCoordinacionSemana: (lunes: string, marca?: string, signal?: AbortSignal) =>
    peticion<RespuestaCoordinacionSemana>(
      `/rota/semana/${encodeURIComponent(lunes)}/coordinacion${query({ marca })}`,
      { signal },
    ),
  setCoordinador: (cuerpo: CuerpoSetCoordinador) =>
    peticion<CoordinacionTurno>("/rota/coordinacion", { metodo: "PUT", json: cuerpo }),
  quitarCoordinador: (cuerpo: CuerpoQuitarCoordinador) =>
    peticion<{ ok: true; borrado: boolean }>("/rota/coordinacion", {
      metodo: "DELETE",
      json: cuerpo,
    }),

  // --- Gestión de turnos: ausencias / vacaciones (F4 · #144, ola A) ---
  rotaAusencias: (params: { miembro_id?: string } = {}, signal?: AbortSignal) =>
    peticion<RespuestaAusenciasRota>(`/rota/ausencias${query(params)}`, { signal }),
  crearAusenciaRota: (cuerpo: CuerpoCrearAusenciaRota) =>
    peticion<RespuestaAusenciaRota>("/rota/ausencias", { metodo: "POST", json: cuerpo }),
  actualizarAusenciaRota: (id: string, cuerpo: CuerpoActualizarAusenciaRota) =>
    peticion<RespuestaAusenciaRota>(`/rota/ausencias/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarAusenciaRota: (id: string) =>
    peticion<RespuestaMensaje>(`/rota/ausencias/${encodeURIComponent(id)}`, { metodo: "DELETE" }),

  // --- Catálogo de programas (#150 PARRILLA 2026.xlsx) ---
  // Las piezas referencian programas por NOMBRE; renombrar hace cascada
  // transaccional sobre rota_piezas.programa. Borrar con piezas en uso requiere
  // ?forzar=true (el 409 incluye `piezas_afectadas` y `en_uso:true`).
  listarProgramasRota: (
    params: { activo?: boolean } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaProgramasRota>(
      `/rota/programas${query({ activo: params.activo === undefined ? undefined : String(params.activo) })}`,
      { signal },
    ),
  crearProgramaRota: (cuerpo: CuerpoCrearProgramaRota) =>
    peticion<RespuestaProgramaRota>("/rota/programas", { metodo: "POST", json: cuerpo }),
  actualizarProgramaRota: (id: string, cuerpo: CuerpoActualizarProgramaRota) =>
    peticion<RespuestaProgramaRota>(`/rota/programas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarProgramaRota: (id: string, params: { forzar?: boolean } = {}) =>
    peticion<RespuestaMensaje & { piezas_afectadas?: number }>(
      `/rota/programas/${encodeURIComponent(id)}${query({ forzar: params.forzar ? "true" : undefined })}`,
      { metodo: "DELETE" },
    ),

  // --- Copia de semana + panel de carga ---
  copiarSemana: (cuerpo: CuerpoCopiarSemana) =>
    peticion<RespuestaCopiarSemana>("/rota/copiar-semana", { metodo: "POST", json: cuerpo }),
  cargaRota: (params: { lunes: string; marca?: string }, signal?: AbortSignal) =>
    peticion<RespuestaCargaRota>(`/rota/carga${query(params)}`, { signal }),

  // --- Configuración editorial de franjas (#185) ---
  // GRID POR MARCA: la config de franjas es por marca; `marca` viaja como `?marca=`.
  obtenerConfigFranjas: (marca?: string, signal?: AbortSignal) =>
    peticion<RespuestaConfigFranjas>(`/rota/config/franjas${query({ marca })}`, { signal }),
  guardarConfigFranjas: (cuerpo: CuerpoGuardarConfigFranjas, marca?: string) =>
    peticion<RespuestaConfigFranjas>(`/rota/config/franjas${query({ marca })}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),

  // --- Franjas POR SEMANA (modelo "Mundial") ---
  // CRUD de `rota_franjas` (N franjas por semana, solapes permitidos, soporte cruce de
  // medianoche, franja Descanso explicita con `es_descanso=true`). GET inicializa defaults
  // (Mañana/Tarde/Descanso) si la semana esta vacia. POST/PATCH/DELETE exigen admin.
  // GRID POR MARCA: `marca` (query) acota la rejilla; al crear, exige una marca concreta.
  listarFranjasSemana: (lunes: string, marca?: string, signal?: AbortSignal) =>
    peticion<RespuestaFranjasSemana>(
      `/rota/semana/${encodeURIComponent(lunes)}/franjas${query({ marca })}`,
      { signal },
    ),
  crearFranjaSemana: (lunes: string, cuerpo: CuerpoCrearFranjaSemana, marca?: string) =>
    peticion<FranjaSemana>(
      `/rota/semana/${encodeURIComponent(lunes)}/franjas${query({ marca })}`,
      { metodo: "POST", json: cuerpo },
    ),
  actualizarFranjaSemana: (id: string, cuerpo: CuerpoActualizarFranjaSemana) =>
    peticion<FranjaSemana>(`/rota/franjas/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  borrarFranjaSemana: (id: string, opts: { forzar?: boolean } = {}) =>
    peticion<{ ok: true; turnos_borrados?: number }>(
      `/rota/franjas/${encodeURIComponent(id)}${opts.forzar ? "?forzar=true" : ""}`,
      { metodo: "DELETE" },
    ),

  // --- Solicitudes de cambio de turno entre compañeros (#175) ---
  // Flujo: A crea -> B acepta/rechaza -> admin aprueba (ejecuta el swap sobre
  // rota_turnos_trabajo) o rechaza. A puede cancelar mientras no sea terminal.
  // El cliente solo informa; las validaciones de permisos y transiciones las
  // hace el backend (errores 400/403/404/409 con mensaje en español).
  listarSwaps: (filtros: FiltrosSwaps = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwaps>(
      `/rota/swaps${query({
        estado: filtros.estado,
        solicitante_id: filtros.solicitante_id,
        destinatario_id: filtros.destinatario_id,
        mio: filtros.mio ? "true" : undefined,
        marca: filtros.marca,
      })}`,
      { signal },
    ),
  crearSwap: (cuerpo: CuerpoCrearSwap, signal?: AbortSignal) =>
    peticion<RespuestaSwap>("/rota/swaps", { metodo: "POST", json: cuerpo, signal }),
  aceptarSwap: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/aceptar`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  rechazarSwap: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/rechazar`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  aprobarSwap: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/aprobar`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  rechazarSwapAdmin: (id: string, cuerpo: CuerpoDecidirSwap = {}, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/rechazar-admin`, {
      metodo: "POST",
      json: cuerpo,
      signal,
    }),
  cancelarSwap: (id: string, signal?: AbortSignal) =>
    peticion<RespuestaSwap>(`/rota/swaps/${encodeURIComponent(id)}/cancelar`, {
      metodo: "POST",
      signal,
    }),

};
