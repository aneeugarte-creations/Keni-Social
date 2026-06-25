// Fragmento del cliente API: dominio «media». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  CosteMedioArte,
  CuerpoAdjuntarAgencia,
  CuerpoAdjuntarPropio,
  CuerpoAdjuntarStock,
  CuerpoAutorizarStock,
  CuerpoGenerarArte,
  CuerpoGenerarMedia,
  CuerpoGuardarArte,
  RespuestaArte,
  RespuestaArtes,
  RespuestaBuscarAgencias,
  RespuestaBuscarPropio,
  RespuestaBuscarStock,
  RespuestaDispositivosPropio,
  RespuestaGenerarArte,
  RespuestaGeneracion,
  RespuestaMedia,
  RespuestaMensaje,
  RespuestaStock,
} from "@/types";

export const apiMedia = {
  // --- Media (imágenes) ---
  // `categoria` (opcional) = carpeta de destino en el almacén: `fotos` (def) para una foto de
  // pieza, `plantillas` para un asset del editor de plantillas. Así el bucket queda dividido por
  // tipo y se puede limpiar `fotos/` a mano sin tocar plantillas/logos reusables.
  subirMedia: (archivo: File, categoria?: "fotos" | "plantillas") => {
    const form = new FormData();
    form.set("archivo", archivo);
    if (categoria) form.set("categoria", categoria);
    return peticion<RespuestaMedia>("/media", { metodo: "POST", form, timeoutMs: 120_000 });
  },
  generarMedia: (cuerpo: CuerpoGenerarMedia) =>
    peticion<RespuestaGeneracion>("/media/generar", { metodo: "POST", json: cuerpo }),
  /** Ola F: sube un archivo de video a `POST /api/media/video` y devuelve `{id, url}`. */
  subirVideo: (archivo: File) => {
    const form = new FormData();
    form.set("archivo", archivo);
    return peticion<RespuestaMedia>("/media/video", { metodo: "POST", form, timeoutMs: 300_000 });
  },
  /** Descarga una imagen externa (p.ej. la original de un artículo RSS) al almacén y
   *  devuelve su `{id, url}` ya servible/publicable. */
  mediaDesdeUrl: (url: string) =>
    peticion<RespuestaMedia>("/media/desde-url", { metodo: "POST", json: { url } }),

  // --- Galería de artes (objetos de media catalogados para reutilizar) ---
  // Guardar un arte lo PROTEGE del GC de media sin dueño y lo hace seleccionable por marca
  // desde el editor de imagen de una pieza. El `objeto` es UNIQUE: `guardarArte` es idempotente.
  listarArtes: (
    filtros: { marca?: string; tipo?: string; q?: string } = {},
    signal?: AbortSignal,
  ) => peticion<RespuestaArtes>(`/artes${query(filtros)}`, { signal }),
  guardarArte: (cuerpo: CuerpoGuardarArte) =>
    peticion<RespuestaArte>("/artes", { metodo: "POST", json: cuerpo }),
  borrarArte: (id: string, purgar = false) =>
    peticion<RespuestaMensaje>(
      `/artes/${encodeURIComponent(id)}${purgar ? "?purgar=1" : ""}`,
      { metodo: "DELETE" },
    ),

  // --- Lanzamiento manual de ARTE (genera N imágenes a mano para una marca) ---
  // Crea N generaciones de imagen y las ejecuta en 2.º plano; el front sondea cada
  // `GET /api/generaciones/{id}` y, al completarse, lee `resultado={id,url,modelo,coste_usd}`.
  generarArte: (cuerpo: CuerpoGenerarArte) =>
    peticion<RespuestaGenerarArte>("/artes/generar", { metodo: "POST", json: cuerpo }),
  // Coste medio por imagen (USD) para estimar el gasto ANTES de lanzar (`modelo` opcional).
  costeMedioArte: (modelo?: string, signal?: AbortSignal) =>
    peticion<CosteMedioArte>(`/artes/coste-medio${query({ modelo })}`, { signal }),

  // --- Fotos de STOCK (ayuda visual NUNCA publicable sin autorizar) ---
  // Busca candidatas en APIs gratuitas (Pexels/Pixabay/Wikimedia/NASA/Openverse). Devuelve los
  // proveedores con su disponibilidad (chips) y las candidatas (referencias, aún sin descargar).
  buscarStock: (
    filtros: { q?: string; proveedor?: string; limite?: number; marca?: string } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaBuscarStock>(
      `/artes/stock/buscar${query({
        q: filtros.q,
        proveedor: filtros.proveedor,
        limite: filtros.limite != null ? String(filtros.limite) : undefined,
        // La marca acota las fuentes a las habilitadas para ella (toggles de la etapa Stock).
        marca: filtros.marca,
      })}`,
      { signal },
    ),
  // Descarga una candidata (o la imagen original de la fuente con `usar_fuente`) y la adjunta a la
  // pieza como AYUDA VISUAL: queda `imagen_origen="stock"`, sin autorizar y con `falta_imagen` activo.
  adjuntarStock: (cuerpo: CuerpoAdjuntarStock) =>
    peticion<RespuestaStock>("/artes/stock/adjuntar", { metodo: "POST", json: cuerpo }),
  // Confirma (o revoca) los derechos para publicar una foto de stock. Autorizar limpia `falta_imagen`.
  autorizarStock: (cuerpo: CuerpoAutorizarStock) =>
    peticion<RespuestaStock>("/artes/stock/autorizar", { metodo: "POST", json: cuerpo }),

  // --- Fotos de AGENCIA LICENCIADAS (publicables con CRÉDITO/BYLINE obligatorio) ---
  // Busca candidatas licenciadas en agencias (AFP). Devuelve los proveedores con su disponibilidad
  // y motivo (sin credenciales, `disponible:false` y `candidatos:[]`) y las candidatas a adjuntar.
  buscarAgencias: (
    filtros: { q?: string; limite?: number } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaBuscarAgencias>(
      `/artes/agencias/buscar${query({
        q: filtros.q,
        limite: filtros.limite != null ? String(filtros.limite) : undefined,
      })}`,
      { signal },
    ),
  // Descarga una candidata licenciada y la adjunta a la pieza como imagen PUBLICABLE
  // (`imagen_origen="licenciada"`, `imagen_autorizada=true`, `falta_imagen=false`) con su crédito.
  adjuntarAgencia: (cuerpo: CuerpoAdjuntarAgencia) =>
    peticion<RespuestaStock>("/artes/agencias/adjuntar", { metodo: "POST", json: cuerpo }),

  // --- Fotos PROPIAS (galería local del equipo, vía el túnel keni-fotos; solo Claro Sports) ---
  // Hace fan-out a las apps de escritorio conectadas del usuario y agrega sus candidatas. El
  // proveedor «propio» trae su disponibilidad (≥1 dispositivo conectado) y el nº de dispositivos.
  buscarPropio: (
    filtros: { q?: string; limite?: number; marca?: string } = {},
    signal?: AbortSignal,
  ) =>
    peticion<RespuestaBuscarPropio>(
      `/artes/propio/buscar${query({
        q: filtros.q,
        limite: filtros.limite != null ? String(filtros.limite) : undefined,
        marca: filtros.marca,
      })}`,
      { signal },
    ),
  // Pide el ORIGINAL por el túnel (no por URL), lo sube a keni-media y lo adjunta como imagen
  // PUBLICABLE (`imagen_origen="propia"`). Identifica la foto por galería + archivo.
  adjuntarPropio: (cuerpo: CuerpoAdjuntarPropio) =>
    peticion<RespuestaStock>("/artes/propio/adjuntar", { metodo: "POST", json: cuerpo }),
  // Apps de escritorio conectadas del usuario, con sus galerías (para la página Galería).
  dispositivosPropio: (signal?: AbortSignal) =>
    peticion<RespuestaDispositivosPropio>("/artes/propio/dispositivos", { signal }),
};
