// Tipos del DOCUMENTO de capas del editor profesional — espejo de
// `motores/estudio_imagen/documento.py`. El editor (react-konva) edita estos objetos en local
// y el servidor los re-renderiza con el MISMO dibujante (`render_node/dibujar.mjs`).
//
// Mantener sincronizado con el esquema Python: cualquier campo nuevo debe existir en ambos lados
// (el validador Python es la fuente de verdad; este fichero es el contrato del cliente).

export const VERSION = 1;

export type TipoCapa = "imagen" | "texto" | "logo" | "marco" | "overlay" | "grupo";
export type Ajuste = "cover" | "contain";
export type Alineacion = "izquierda" | "centro" | "derecha" | "justificado";
// Catálogo de FORMAS compartido (marcos e imágenes). Espejo de `pathForma` en `dibujar.mjs` y de
// `_FORMAS` en `documento.py`. "rect"/"elipse" son retrocompatibles con documentos antiguos.
export type Forma = "rect" | "elipse" | "triangulo" | "rombo" | "pentagono" | "hexagono" | "estrella" | "flecha";
export const CATALOGO_FORMAS: Forma[] = [
  "rect", "elipse", "triangulo", "rombo", "pentagono", "hexagono", "estrella", "flecha",
];
export const ETIQUETA_FORMA: Record<Forma, string> = {
  rect: "Rectángulo",
  elipse: "Círculo",
  triangulo: "Triángulo",
  rombo: "Rombo",
  pentagono: "Pentágono",
  hexagono: "Hexágono",
  estrella: "Estrella",
  flecha: "Flecha",
};
// El marco además admite "linea" (un trazo recto), que no es una forma rellenable.
export type FormaMarco = Forma | "linea";
export type BindingTexto = "copy_in" | "etiqueta_default" | null;

// Modo de fusión de una capa (espejo del `MAPA_MEZCLA` de `dibujar.mjs`). La etiqueta interna es
// en español; el render la traduce a `globalCompositeOperation`. "normal" = source-over (default).
export type TipoMezcla = "normal" | "multiplicar" | "trama" | "superponer" | "aclarar" | "oscurecer";

// Etiquetas legibles de cada modo de fusión para la UI (orden del select del inspector).
export const ETIQUETA_MEZCLA: Record<TipoMezcla, string> = {
  normal: "Normal",
  multiplicar: "Multiplicar",
  trama: "Trama",
  superponer: "Superponer",
  aclarar: "Aclarar",
  oscurecer: "Oscurecer",
};

// Rol de un texto en la plantilla: qué dato de la pieza lo rellena al aplicarla. `null` = texto fijo.
export const ETIQUETA_BINDING: Record<"fijo" | "copy_in" | "etiqueta_default", string> = {
  fijo: "Texto fijo",
  copy_in: "Titular (copy)",
  etiqueta_default: "Pleca / etiqueta",
};

// Una parada de un degradado multi-stop: posición 0..1 + color.
export interface ParadaDegradado {
  pos: number;
  color: string;
}
// Degradado reutilizable (fondo/texto/marco): lineal (def) o radial; multi-stop opcional.
// Retrocompat: `desde`/`hasta`/`angulo` siguen mandando si no hay `stops`; `tipo` ausente = lineal.
export interface Degradado {
  desde: string;
  hasta: string;
  angulo?: number; // grados (def 180 = vertical ↓). Solo lineal.
  tipo?: "lineal" | "radial"; // def "lineal"
  stops?: ParadaDegradado[]; // multi-parada; si está, manda sobre desde/hasta
}

export interface Fondo {
  tipo: "color" | "degradado" | "imagen";
  color?: string;
  degradado?: Degradado;
  imagen?: { media_id: string; ajuste?: Ajuste };
}

export interface CapaBase {
  id: string;
  tipo: TipoCapa;
  nombre?: string; // etiqueta editable en el panel de capas (el render la ignora)
  x: number;
  y: number;
  w: number;
  h: number;
  rotacion: number;
  opacidad: number; // 0..1
  mezcla?: TipoMezcla; // modo de fusión (def "normal" = source-over). Solo se persiste si != "normal".
  z: number;
  visible: boolean;
  bloqueada: boolean;
}

// Tinte DUOTONO de marca: mapea la luminancia de la foto entre `sombra` (oscuros) y `luz` (claros).
export interface Duotono {
  sombra: string;
  luz: string;
}

export interface Filtros {
  brillo?: number; // 1 = neutro
  contraste?: number;
  saturacion?: number;
  desenfoque?: number; // px
  duotono?: Duotono | null; // tinte duotono sobre la foto (def null = sin duotono)
}

// Recorte (crop) NO destructivo de una imagen: sub-rect de la FUENTE en fracciones 0..1.
// Default (sin crop) = toda la imagen.
export interface Crop {
  cx: number;
  cy: number;
  cw: number;
  ch: number;
}

export interface CapaImagen extends CapaBase {
  tipo: "imagen";
  objeto: string; // id de media ("" = vacío/placeholder)
  ajuste: Ajuste;
  foco: [number, number];
  zoom: number; // reencuadre dentro del marco (1 = ajuste base)
  es_foto?: boolean; // ESTA capa es el hueco de foto de la plantilla (única; obligatoria en el estudio)
  forma?: Forma; // recorte de la imagen: catálogo de formas (rect def, elipse/círculo, polígonos…)
  radio?: number; // radio de esquinas redondeadas para rect, en px (def 0; ignorado si forma!=rect)
  radios?: [number, number, number, number]; // radio por esquina [tl,tr,br,bl]; si está, manda sobre `radio`
  crop?: Crop; // recorte no destructivo de la fuente (def: sin crop = toda la imagen)
  filtros: Filtros | null;
  sombra?: Sombra | null; // sombra del rectángulo de la imagen (opcional)
  flip_h?: boolean; // volteo horizontal (espejo izq<->der) alrededor del centro. Def false; solo se persiste si true.
  flip_v?: boolean; // volteo vertical (espejo arriba<->abajo) alrededor del centro. Def false; solo se persiste si true.
}

export interface Sombra {
  dx: number;
  dy: number;
  color: string;
  desenfoque?: number; // blur px (def 0). >0 activa la sombra real del canvas.
  opacidad?: number; // 0..1 (def 1). <1 activa la sombra real del canvas.
}
// Relleno por degradado (texto/marco). Sustituye al color sólido cuando está presente. Soporta
// lineal/radial y multi-stop (mismo contrato que el degradado de fondo).
export type RellenoDegradado = Degradado;
export interface Chip {
  color: string;
  pad_x: number;
  pad_y: number;
  radio: number;
}
export interface Contorno {
  color: string;
  grosor: number;
}

export interface CapaTexto extends CapaBase {
  tipo: "texto";
  texto: string;
  binding: BindingTexto;
  familia: string;
  tamano: number;
  peso: number;
  // CURSIVA (itálica real). Solo surte efecto en familias con itálica registrada
  // (`FAMILIAS_CON_CURSIVA` en dibujar.mjs): para el resto el editor deshabilita el botón y ambos
  // renders ignoran el flag (nadie sintetiza oblicuas). Opcional; default false (solo se persiste si true).
  cursiva?: boolean;
  // SUBRAYADO: línea bajo cada línea de texto (grosor ∝ tamaño, color del relleno), pintada igual
  // por el editor (Konva `textDecoration`) y el export (`dibujarDecoracionLinea` en dibujar.mjs).
  // El texto en arco (`curva`) no se subraya en ningún lado. Opcional; default false (solo se persiste si true).
  subrayado?: boolean;
  // TACHADO: línea a MEDIA altura de cada línea de texto (misma geometría que el `textDecoration:
  // "line-through"` de Konva; combinable con el subrayado), pintada igual por el editor y el
  // export (`dibujarDecoracionLinea` en dibujar.mjs). El texto en arco no se tacha en ningún lado.
  // Opcional; default false (solo se persiste si true).
  tachado?: boolean;
  color: string;
  alineacion: Alineacion;
  mayusculas: boolean;
  interlineado: number;
  interletra: number; // letter-spacing en px
  auto_ajuste: { max_lineas: number; tam_min: number };
  sombra: Sombra | null;
  relleno_degradado?: RellenoDegradado | null; // degradado del relleno (sustituye a `color`)
  // Texto curvo (texto en arco): si está presente y `radio != 0`, el texto se dibuja a lo largo de
  // un ARCO (una sola línea; ignora wrap/justificado). `radio` en px: positivo = arco hacia arriba
  // (sonrisa), negativo = hacia abajo (ceño); |radio| grande = casi recto. Ausente/null = recto.
  curva?: { radio: number } | null;
  contorno: Contorno | null;
  chip: Chip | null;
  ancla: "arriba" | "abajo";
  // Alineación VERTICAL del texto dentro de la CAJA (cuando `h>0`). La caja es de alto fijo e
  // inamovible: el texto se auto-encoge para caber y se posiciona arriba/centro/abajo dentro de
  // ella. `ancla` se mantiene por compatibilidad (camino legado h<=0).
  valign: "arriba" | "centro" | "abajo";
}

export interface CapaLogo extends CapaBase {
  tipo: "logo";
  tipo_logo: "imagen" | "wordmark";
  media_id: string;
  wordmark: { texto: string; color: string; fondo: string; familia: string; peso: number };
  flip_h?: boolean; // volteo horizontal (espejo izq<->der) alrededor del centro. Def false; solo se persiste si true.
  flip_v?: boolean; // volteo vertical (espejo arriba<->abajo) alrededor del centro. Def false; solo se persiste si true.
}

export interface CapaMarco extends CapaBase {
  tipo: "marco";
  forma: FormaMarco;
  relleno: string | null;
  relleno_degradado?: RellenoDegradado | null; // degradado del relleno (sustituye a `relleno`)
  borde: { color: string; grosor: number } | null;
  radio: number;
  radios?: [number, number, number, number]; // radio por esquina [tl,tr,br,bl]; si está, manda sobre `radio`
  sombra?: Sombra | null; // sombra de la forma del marco (opcional)
}

export interface CapaOverlay extends CapaBase {
  tipo: "overlay";
  color: string;
  alto_frac: number;
  alpha: number;
  // Borde al que se pega la banda: "abajo" (def, banda inferior, opaca abajo) o "arriba" (banda
  // superior, opaca arriba). Solo se persiste si "arriba" (retrocompat: los overlays históricos
  // no lo llevan y son inferiores).
  lado?: "arriba" | "abajo";
}

export interface CapaGrupo extends CapaBase {
  tipo: "grupo";
  capas: Capa[];
}

export type Capa = CapaImagen | CapaTexto | CapaLogo | CapaMarco | CapaOverlay | CapaGrupo;

export interface Documento {
  version: number;
  marca: string;
  fuentes: { sans: string; condensada: string };
  // `safe_left`/`safe_right` (márgenes laterales) son ADITIVOS y opcionales: documentos antiguos
  // sin ellos => 0. Espejo de `_validar_formato` en `documento.py`.
  formato: { w: number; h: number; safe_top: number; safe_bottom: number; safe_left?: number; safe_right?: number };
  fondo: Fondo;
  capas: Capa[];
}

// Catálogo de fuentes embebidas ofrecidas por el editor (espejo de `fuentes.mjs::CATALOGO` y
// `spec_plantilla.CATALOGO_FUENTES`). Las tipografías propias por marca (frente D) se añaden en runtime.
export const CATALOGO_FUENTES = [
  "Barlow",
  "Barlow Condensed",
  "Anton",
  "Oswald",
  "Montserrat",
  "Archivo Black",
  "Lora",
  "Exo 2",
  "Lato",
  "Poppins",
  "Roboto Condensed",
  "Mulish",
  "Nunito Sans",
] as const;

// ---------------------------------------------------------------------------
// Factories — nuevas capas con valores por defecto razonables.
// ---------------------------------------------------------------------------

let _seq = 0;
export function nuevoId(prefijo: string): string {
  _seq += 1;
  return `${prefijo}-${Date.now().toString(36)}-${_seq}`;
}

function base(tipo: TipoCapa, x: number, y: number, w: number, h: number, z: number): CapaBase {
  return { id: nuevoId(tipo), tipo, x, y, w, h, rotacion: 0, opacidad: 1, z, visible: true, bloqueada: false };
}

export function nuevaCapaTexto(parcial: Partial<CapaTexto> = {}): CapaTexto {
  return {
    ...base("texto", 80, 80, 600, 0, 20),
    tipo: "texto",
    texto: "Texto",
    binding: null,
    familia: "Barlow",
    tamano: 64,
    peso: 700,
    color: "#FFFFFF",
    alineacion: "izquierda",
    mayusculas: false,
    interlineado: 1.14,
    interletra: 0,
    auto_ajuste: { max_lineas: 4, tam_min: 40 },
    sombra: null,
    contorno: null,
    chip: null,
    ancla: "arriba",
    valign: "centro",
    ...parcial,
  };
}

export function nuevaCapaImagen(objeto: string, parcial: Partial<CapaImagen> = {}): CapaImagen {
  return {
    ...base("imagen", 0, 0, 1080, 1080, 0),
    tipo: "imagen",
    objeto,
    ajuste: "cover",
    foco: [0.5, 0.5],
    zoom: 1,
    filtros: null,
    ...parcial,
  };
}

export function nuevaCapaMarco(parcial: Partial<CapaMarco> = {}): CapaMarco {
  return {
    ...base("marco", 80, 80, 400, 240, 15),
    tipo: "marco",
    forma: "rect",
    relleno: null,
    borde: { color: "#FFFFFF", grosor: 6 },
    radio: 0,
    ...parcial,
  };
}

export function nuevaCapaLogo(media_id: string, parcial: Partial<CapaLogo> = {}): CapaLogo {
  return {
    ...base("logo", 56, 56, 220, 96, 30),
    tipo: "logo",
    tipo_logo: media_id ? "imagen" : "wordmark",
    media_id,
    wordmark: { texto: "", color: "#FFFFFF", fondo: "#E30613", familia: "Barlow", peso: 700 },
    ...parcial,
  };
}

export function nuevaCapaOverlay(parcial: Partial<CapaOverlay> = {}): CapaOverlay {
  return {
    ...base("overlay", 0, 0, 1080, 1080, 10),
    tipo: "overlay",
    color: "#000000",
    alto_frac: 0.45,
    alpha: 200,
    ...parcial,
  };
}

export function documentoVacio(
  formato: { w: number; h: number; safe_top: number; safe_bottom: number; safe_left?: number; safe_right?: number },
  marca = "",
): Documento {
  // Un lienzo nuevo nace LIMPIO y TRANSPARENTE (fondo `#00000000` => se ve el tablero y exporta con
  // alfa). Trae su HUECO DE FOTO (obligatorio para guardar plantilla) pero OCULTO: así no pinta el
  // placeholder gris que tapaba todo y parecía "prediseñado". El usuario lo muestra (ojo en el panel
  // de capas) cuando quiere colocar la foto.
  const hueco = nuevaCapaImagen("", {
    id: "foto",
    x: 0,
    y: 0,
    w: formato.w,
    h: formato.h,
    z: 0,
    es_foto: true,
    bloqueada: true,
    visible: false,
    nombre: "Foto",
  });
  return {
    version: VERSION,
    marca,
    fuentes: { sans: "Barlow", condensada: "Barlow Condensed" },
    formato,
    fondo: { tipo: "color", color: "#00000000" },
    capas: [hueco],
  };
}

// z máximo + 1, para insertar una capa nueva encima de todo.
export function zTope(doc: Documento): number {
  return doc.capas.reduce((m, c) => Math.max(m, c.z ?? 0), 0) + 1;
}

// ¿Tiene el documento algún HUECO DE FOTO (`es_foto`) sin `objeto` asignado? Los huecos viven al
// NIVEL SUPERIOR de `capas` (mismo contrato que `capas_foto` del back y que la "Vista con muestra":
// `CapaNodo` solo rellena con la muestra los `es_foto` de nivel superior, no los anidados en grupos).
export function tieneHuecoFotoVacio(doc: Documento): boolean {
  return doc.capas.some(
    (c) => c.tipo === "imagen" && c.es_foto === true && !(c.objeto || "").trim(),
  );
}

// Copia del documento con `objeto` puesto en cada HUECO DE FOTO vacío de nivel superior. Sirve para
// HORNEAR la foto de muestra SOLO en la descarga (export WYSIWYG): no muta el documento editable ni
// lo que se guarda como plantilla/pieza, donde el hueco debe seguir vacío para recibir la foto real.
export function conFotoEnHuecosVacios(doc: Documento, objeto: string): Documento {
  return {
    ...doc,
    capas: doc.capas.map((c) =>
      c.tipo === "imagen" && c.es_foto === true && !(c.objeto || "").trim()
        ? { ...c, objeto }
        : c,
    ),
  };
}

// Copia del documento con el TEXTO de cada capa de texto de nivel superior CONGELADO según `resolver`
// (devuelve el texto a hornear, o `null` para dejar la capa como está). A la capa horneada se le
// quita el `binding`: así el render del servidor pinta ese `texto` literal en vez del valor del
// binding (que sin pieza llega vacío). Sirve para que la descarga sea WYSIWYG con el titular/pleca
// que se ve en el lienzo, sin tocar el documento editable ni lo que se guarda como plantilla/pieza.
export function conTextosHorneados(
  doc: Documento,
  resolver: (c: CapaTexto) => string | null,
): Documento {
  return {
    ...doc,
    capas: doc.capas.map((c) => {
      if (c.tipo !== "texto") return c;
      const v = resolver(c);
      return v == null ? c : { ...c, texto: v, binding: null };
    }),
  };
}

// Alto VISUAL de una capa para centrar/repartir: los textos sin caja (h<=0) ocupan una línea
// (tamano × interlineado); el overlay solo pinta su BANDA inferior; el resto usa su h del modelo.
export function altoVisual(c: Capa): number {
  if (c.tipo === "overlay") return bandaOverlay(c);
  return c.tipo === "texto" && c.h <= 0 ? Math.round(c.tamano * c.interlineado) : c.h;
}

// Alto en px de la BANDA visible de un overlay (degradado de legibilidad pegado al fondo de su
// caja). Espejo EXACTO del export (`dibujarOverlayInferior` en dibujar.mjs:
// max(1, floor(h * alto_frac)) con default 0.58), INCLUIDO el floor. Única fuente de la fórmula
// en el cliente.
export function bandaOverlay(c: CapaOverlay): number {
  return Math.max(1, Math.floor(c.h * (c.alto_frac ?? 0.58)));
}

// Caja VISIBLE de una capa en coords del documento, SIN rotar (la rotación pivota en (c.x, c.y),
// igual que el export). Donde el modelo y lo pintado difieren: el overlay solo pinta su banda
// inferior (y + h - banda) y el texto sin caja (h<=0) ocupa el alto de una línea — con ancla
// "abajo" su `y` almacenada es el borde INFERIOR del bloque (contrato legado del export). La usan
// inspector, imanes, marquee, alinear/distribuir y la etiqueta del gesto para operar sobre LO QUE
// SE VE, convirtiendo al escribir (el contrato de almacenamiento no cambia).
export function cajaVisual(c: Capa): { x: number; y: number; w: number; h: number } {
  if (c.tipo === "overlay") {
    const banda = bandaOverlay(c);
    // La banda se pega ARRIBA (y = c.y) o ABAJO (y = c.y + c.h - banda, def).
    const y = c.lado === "arriba" ? c.y : c.y + c.h - banda;
    return { x: c.x, y, w: c.w, h: banda };
  }
  if (c.tipo === "texto" && c.h <= 0) {
    const alto = altoVisual(c);
    return { x: c.x, y: c.ancla === "abajo" ? c.y - alto : c.y, w: c.w, h: alto };
  }
  return { x: c.x, y: c.y, w: c.w, h: c.h };
}
