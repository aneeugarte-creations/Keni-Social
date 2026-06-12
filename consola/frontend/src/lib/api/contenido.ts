// Fragmento del cliente API: dominio «contenido». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion } from "./_core";
import type {
  CuerpoActualizarContenido,
  CuerpoActualizarPlataforma,
  CuerpoAportarMaterial,
  CuerpoCrearContenido,
  CuerpoCrearPostDirecto,
  CuerpoSugerirHora,
  RespuestaContenido,
  RespuestaContenidoItem,
  RespuestaEtiquetasContenido,
  RespuestaMensaje,
  RespuestaPlataforma,
  RespuestaSugerirHora,
} from "@/types";

export const apiContenido = {
  // --- Tablero de contenido unificado (herramienta de community manager) ---
  contenido: (
    params: {
      flujo?: string;
      marca?: string;
      responsable_id?: string;
      estado?: string;
      clase?: string;
      etiqueta?: string;
      desde?: string;
      hasta?: string;
    } = {},
    signal?: AbortSignal,
  ) => {
    const qs = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") qs.set(k, String(v));
    }
    const cola = qs.toString();
    return peticion<RespuestaContenido>(`/contenido${cola ? `?${cola}` : ""}`, { signal });
  },
  crearContenido: (cuerpo: CuerpoCrearContenido) =>
    peticion<RespuestaContenidoItem>("/contenido", { metodo: "POST", json: cuerpo }),
  actualizarContenido: (id: string, cuerpo: CuerpoActualizarContenido) =>
    peticion<RespuestaContenidoItem>(`/contenido/${encodeURIComponent(id)}`, {
      metodo: "PATCH",
      json: cuerpo,
    }),
  eliminarContenido: (id: string) =>
    peticion<RespuestaMensaje>(`/contenido/${encodeURIComponent(id)}`, { metodo: "DELETE" }),
  /** "La lista" (reparto ClaroSports): COGE el tema (claim atómico sobre el `contenido`
   *  padre: todas sus redes pasan a ser tuyas). 409 si otra persona ya lo cogió. */
  cogerContenido: (contenidoId: string) =>
    peticion<RespuestaContenidoItem>(`/contenido/${encodeURIComponent(contenidoId)}/coger`, {
      metodo: "POST",
    }),
  /** Suelta el tema (vuelve a "por coger"). Solo quien lo cogió, o un admin. */
  soltarContenido: (contenidoId: string) =>
    peticion<RespuestaContenidoItem>(`/contenido/${encodeURIComponent(contenidoId)}/soltar`, {
      metodo: "POST",
    }),
  /** "La lista" (reparto ClaroSports): el MANAGER (admin) EMPUJA el tema a una persona
   *  concreta —o lo REASIGNA pisando a quien lo tuviera—. Es la otra puerta del mismo
   *  responsable: `cogerContenido` es el self-claim del empleado; esto es el push de Elias.
   *  El asignado recibe aviso in-app. 403 si no eres manager; 400 sin persona (libera con soltar). */
  asignarContenido: (contenidoId: string, responsableId: string) =>
    peticion<RespuestaContenidoItem>(`/contenido/${encodeURIComponent(contenidoId)}/asignar`, {
      metodo: "POST",
      json: { responsable_id: responsableId },
    }),
  /** Tareas: registra la COBERTURA de un evento (de la rota) — find-or-create idempotente de
   *  su tarea y la coge (self-claim) o, si pasas responsableId siendo manager, la asigna a esa
   *  persona y le avisa. Es lo que convierte un evento «Por cubrir» en una tarea con dueño. */
  cubrirEvento: (eventoId: string, responsableId?: string) =>
    peticion<RespuestaContenidoItem>("/contenido/cubrir-evento", {
      metodo: "POST",
      json: { evento_id: eventoId, responsable_id: responsableId },
    }),
  agregarPlataforma: (contenidoId: string, red: string) =>
    peticion<RespuestaPlataforma>(
      `/contenido/${encodeURIComponent(contenidoId)}/plataformas`,
      { metodo: "POST", json: { red } },
    ),
  actualizarPlataforma: (
    contenidoId: string,
    plataformaId: string,
    cuerpo: CuerpoActualizarPlataforma,
  ) =>
    peticion<RespuestaPlataforma>(
      `/contenido/${encodeURIComponent(contenidoId)}/plataformas/${encodeURIComponent(plataformaId)}`,
      { metodo: "PATCH", json: cuerpo },
    ),
  // Genera una imagen adaptada por red (recorte al formato + plantilla de marca) a partir de
  // `imagen` y la asigna a CADA plataforma de la pieza, de forma determinista.
  adaptarImagenContenido: (contenidoId: string, imagen: string) =>
    peticion<{ adaptadas: number }>(
      `/contenido/${encodeURIComponent(contenidoId)}/adaptar-imagen`,
      { metodo: "POST", json: { imagen } },
    ),
  eliminarPlataforma: (contenidoId: string, plataformaId: string) =>
    peticion<RespuestaMensaje>(
      `/contenido/${encodeURIComponent(contenidoId)}/plataformas/${encodeURIComponent(plataformaId)}`,
      { metodo: "DELETE" },
    ),
  // PUERTA CREATIVA (Fase 1 / Flujo A): el equipo "postea" material ORIGINAL (foto/nota/idea/
  // url) con marca. Crea un contenido con origen='equipo' que ENCIENDE la auto-generación de
  // copy automáticamente. Multipart porque puede llevar la foto que el equipo trae de fuera.
  aportarMaterial: (cuerpo: CuerpoAportarMaterial) => {
    const form = new FormData();
    // Título OPCIONAL: solo se manda si el equipo lo dio; si no, el backend lo deriva.
    if (cuerpo.titulo) form.set("titulo", cuerpo.titulo);
    form.set("marca", cuerpo.marca);
    if (cuerpo.material) form.set("material", cuerpo.material);
    if (cuerpo.url) form.set("url", cuerpo.url);
    if (cuerpo.intencion) form.set("intencion", cuerpo.intencion);
    if (cuerpo.redes?.length) form.set("redes", cuerpo.redes.join(","));
    if (cuerpo.imagen) form.set("imagen", cuerpo.imagen);
    // Vídeo/audio: se transcribe EN LOCAL en el back y el texto alimenta el auto-copy.
    if (cuerpo.clip) form.set("clip", cuerpo.clip);
    return peticion<RespuestaContenidoItem>("/contenido/aportar", {
      metodo: "POST",
      form,
      timeoutMs: 120_000,
    });
  },
  // ALTA DIRECTA de un post desde el feed: el equipo teclea el COPY FINAL y nace un
  // borrador por red por el MISMO motor que el copy generado (sin generación: el copy es
  // del humano). La pieza sigue el flujo normal (arte, revisión, programación).
  crearPostDirecto: (cuerpo: CuerpoCrearPostDirecto) =>
    peticion<RespuestaContenidoItem>("/contenido/post-directo", { metodo: "POST", json: cuerpo }),
  // Fase3 auto-planificación: sugerir la mejor hora de publicación (1 clic en la UI).
  sugerirHora: (cuerpo: CuerpoSugerirHora) =>
    peticion<RespuestaSugerirHora>("/planificacion/sugerir-hora", { metodo: "POST", json: cuerpo }),
  asignarEtiquetaContenido: (contenidoId: string, etiqueta_id: string) =>
    peticion<RespuestaEtiquetasContenido>(
      `/contenido/${encodeURIComponent(contenidoId)}/etiquetas`,
      { metodo: "POST", json: { etiqueta_id } },
    ),
  quitarEtiquetaContenido: (contenidoId: string, etiquetaId: string) =>
    peticion<RespuestaEtiquetasContenido>(
      `/contenido/${encodeURIComponent(contenidoId)}/etiquetas/${encodeURIComponent(etiquetaId)}`,
      { metodo: "DELETE" },
    ),

};
