/**
 * Datos de muestra para la vista previa del Informe (deck PDF de Métricas). Construye las
 * ENTRADAS crudas con la MISMA forma que el backend (los pares [queryKey, data] que alimentan
 * `desdeEntradas` en producción), para ver el deck real con cifras plausibles y deterministas.
 * No toca red ni backend; solo sirve para iterar el diseño en localhost.
 */

type Entrada = [readonly unknown[], unknown];

/** Día ISO del periodo de muestra (junio 2026). */
function iso(dia: number): string {
  return `2026-06-${String(dia).padStart(2, "0")}`;
}

/** Serie diaria suave y determinista con un pico marcado (base + onda + spike puntual). */
function serieDiaria(
  n: number,
  base: number,
  amplitud: number,
  spikeDia: number,
  spikeMult: number,
): number[] {
  return Array.from({ length: n }, (_, i) => {
    const onda = Math.sin((i / n) * Math.PI * 3) * amplitud;
    const deriva = (i / n) * amplitud * 0.5;
    const v = base + onda + deriva;
    return Math.round(i + 1 === spikeDia ? v * spikeMult : v);
  });
}

/** Reparto de visualizaciones por red para un volumen total dado. */
function repartoRedes(vistas: number): Array<{ red: string; visualizaciones: number }> {
  const pesos: Record<string, number> = {
    facebook: 0.34,
    tiktok: 0.29,
    instagram: 0.2,
    youtube: 0.11,
    x: 0.06,
  };
  return Object.entries(pesos).map(([red, p]) => ({ red, visualizaciones: Math.round(vistas * p) }));
}

interface PerfilMarca {
  id: string;
  marca: string;
  vistas: number;
  alcance: number;
  interacciones: number;
  engagement: number;
  piezas: number;
  seguidoresInicio: number;
  seguidoresFin: number;
}

const PERFILES: Record<string, PerfilMarca> = {
  unotv: {
    id: "unotv",
    marca: "UnoTV",
    vistas: 48_200_000,
    alcance: 31_500_000,
    interacciones: 1_340_000,
    engagement: 2.78,
    piezas: 642,
    seguidoresInicio: 8_420_000,
    seguidoresFin: 8_612_000,
  },
  "claro-sports": {
    id: "claro-sports",
    marca: "Claro Sports",
    vistas: 35_600_000,
    alcance: 22_900_000,
    interacciones: 1_010_000,
    engagement: 2.84,
    piezas: 488,
    seguidoresInicio: 6_120_000,
    seguidoresFin: 6_268_000,
  },
  "nacion-gamer": {
    id: "nacion-gamer",
    marca: "Nación Gamer",
    vistas: 15_400_000,
    alcance: 9_800_000,
    interacciones: 540_000,
    engagement: 3.5,
    piezas: 312,
    seguidoresInicio: 2_140_000,
    seguidoresFin: 2_205_000,
  },
  "piso-15": {
    id: "piso-15",
    marca: "Piso 15",
    vistas: 8_700_000,
    alcance: 5_400_000,
    interacciones: 310_000,
    engagement: 3.6,
    piezas: 208,
    seguidoresInicio: 1_180_000,
    seguidoresFin: 1_232_000,
  },
  fundacion: {
    id: "fundacion",
    marca: "Fundación",
    vistas: 5_300_000,
    alcance: 3_600_000,
    interacciones: 168_000,
    engagement: 3.2,
    piezas: 144,
    seguidoresInicio: 820_000,
    seguidoresFin: 851_000,
  },
};

const TITULARES: Record<string, Array<{ titulo: string; plataforma: string; dia: number }>> = {
  unotv: [
    { titulo: "Sismo de magnitud 5.9 sacude la CDMX esta madrugada", plataforma: "facebook", dia: 18 },
    { titulo: "VIDEO: rescatan a familia atrapada por las lluvias en Edomex", plataforma: "tiktok", dia: 12 },
    { titulo: "Sheinbaum anuncia nuevo plan de seguridad para el Valle de México", plataforma: "instagram", dia: 6 },
    { titulo: "Clima HOY: se esperan tormentas fuertes en 14 estados", plataforma: "facebook", dia: 22 },
    { titulo: "Así quedó la avenida tras el socavón en Iztapalapa", plataforma: "youtube", dia: 9 },
    { titulo: "Detienen a presunto líder de banda de robo a casa habitación", plataforma: "x", dia: 15 },
    { titulo: "Tipo de cambio HOY: el dólar cierra la jornada al alza", plataforma: "instagram", dia: 27 },
    { titulo: "Megamarcha en el Zócalo: minuto a minuto", plataforma: "tiktok", dia: 3 },
  ],
  "claro-sports": [
    { titulo: "GOLAZO de último minuto: el resumen del clásico", plataforma: "tiktok", dia: 14 },
    { titulo: "México convoca a su lista para el amistoso de junio", plataforma: "instagram", dia: 7 },
    { titulo: "Checo Pérez y un fin de semana para el olvido en el GP", plataforma: "facebook", dia: 19 },
    { titulo: "Entrevista exclusiva con el técnico tras la victoria", plataforma: "youtube", dia: 11 },
    { titulo: "Las mejores jugadas de la jornada en 60 segundos", plataforma: "tiktok", dia: 23 },
    { titulo: "Tabla de posiciones: así marcha la Liga MX", plataforma: "x", dia: 5 },
    { titulo: "Resumen NBA: la final que paralizó la madrugada", plataforma: "instagram", dia: 25 },
    { titulo: "Fichaje confirmado: llega refuerzo de Europa", plataforma: "facebook", dia: 2 },
  ],
};

/** Construye las entradas crudas (queryKey + data) para una marca individual. */
/** URL de muestra plausible al post en su red (solo preview; en prod viene del backend). */
function urlMuestra(marcaId: string, red: string, i: number): string {
  const slug = marcaId.replace(/-/g, "");
  const id = `1807${i}4920${i}`;
  switch (red) {
    case "facebook":
      return `https://www.facebook.com/${slug}/posts/${id}`;
    case "instagram":
      return `https://www.instagram.com/p/C${slug.slice(0, 3)}${i}x8Ka/`;
    case "tiktok":
      return `https://www.tiktok.com/@${slug}/video/73${id}`;
    case "youtube":
      return `https://www.youtube.com/watch?v=${slug.slice(0, 3)}${i}Xb9Qz`;
    case "x":
      return `https://x.com/${slug}/status/18${id}`;
    default:
      return `https://${slug}.com/post/${id}`;
  }
}

/** Formato de muestra según la red (solo preview). */
function formatoMuestra(red: string): string {
  const m: Record<string, string> = {
    tiktok: "video",
    instagram: "reel",
    youtube: "video",
    facebook: "foto",
    x: "texto",
  };
  return m[red] ?? "foto";
}

function entradasMarca(p: PerfilMarca): Entrada[] {
  const n = 30;
  // Tendencia: visualizaciones por día con un pico (pieza viral), interacciones por día acompañando.
  const baseVistas = (p.vistas / n) * 0.7;
  const vistasDia = serieDiaria(n, baseVistas, baseVistas * 0.4, 18, 4.2);
  const baseInter = (p.interacciones / n) * 0.78;
  const interDia = serieDiaria(n, baseInter, baseInter * 0.45, 18, 3.4);
  const tendencia = {
    puntos: Array.from({ length: n }, (_, i) => ({
      fecha: iso(i + 1),
      visualizaciones: vistasDia[i],
      interacciones: interDia[i],
    })),
  };

  // Seguidores: crecimiento suave del inicio al fin del periodo.
  const seguidores = {
    puntos: Array.from({ length: n }, (_, i) => ({
      fecha: iso(i + 1),
      total: Math.round(p.seguidoresInicio + ((p.seguidoresFin - p.seguidoresInicio) * i) / (n - 1)),
    })),
  };

  // Desglose de interacciones por red. La interacción NO es proporcional a las vistas: cada red
  // engancha distinto (TikTok/Instagram más, Facebook menos), para que "dónde engancha mejor"
  // cuente una historia. likes dominan la mezcla; el resto reparte igual en todas.
  const ENG_RATE: Record<string, number> = {
    facebook: 0.018,
    tiktok: 0.047,
    instagram: 0.038,
    youtube: 0.022,
    x: 0.031,
  };
  const celdas = repartoRedes(p.vistas).map(({ red, visualizaciones: vistasRed }) => {
    const inter = Math.round(vistasRed * (ENG_RATE[red] ?? 0.03));
    return {
      marca: p.marca,
      red,
      likes: Math.round(inter * 0.74),
      comentarios: Math.round(inter * 0.09),
      compartidos: Math.round(inter * 0.12),
      guardados: Math.round(inter * 0.05),
    };
  });

  const top = (TITULARES[p.id] ?? []).map((t, i) => {
    const vistas = Math.round(p.vistas * (0.052 - i * 0.004));
    const engagement = Number((4.6 - i * 0.32).toFixed(1));
    return {
      titulo: t.titulo,
      plataforma: t.plataforma,
      publicado: `${String(t.dia).padStart(2, "0")} jun`,
      visualizaciones: vistas,
      interacciones: Math.round((vistas * engagement) / 100),
      engagement_pct: engagement,
      url: urlMuestra(p.id, t.plataforma, i),
      formato: formatoMuestra(t.plataforma),
    };
  });

  const reporte = {
    total: {
      visualizaciones: p.vistas,
      alcance: p.alcance,
      interacciones: p.interacciones,
      engagement_pct: p.engagement,
      piezas: p.piezas,
    },
    por_red: repartoRedes(p.vistas),
  };

  const comparar = {
    total: {
      metricas: [
        { metrica: "visualizaciones", variacion_pct: 14.2 },
        { metrica: "alcance", variacion_pct: 5.1 },
        { metrica: "interacciones", variacion_pct: -3.4 },
        { metrica: "engagement_pct", diferencia: -0.2 },
      ],
    },
  };

  return [
    [["metricas", "reporte"], reporte],
    [["metricas", "comparar"], comparar],
    [["metricas", "tendencia"], tendencia],
    [["metricas", "seguidores"], seguidores],
    [["metricas", "desglose"], { celdas }],
    [["metricas", "piezas"], { top }],
  ];
}

/** Entradas para el modo "Todas las marcas": agrega 5 cuentas y suma totales. */
function entradasTodas(): Entrada[] {
  const cuentas = [
    { marca: "UnoTV", marca_id: "unotv", visualizaciones: 48_200_000 },
    { marca: "Claro Sports", marca_id: "claro-sports", visualizaciones: 35_600_000 },
    { marca: "Nación Gamer", marca_id: "nacion-gamer", visualizaciones: 15_400_000 },
    { marca: "Piso 15", marca_id: "piso-15", visualizaciones: 8_700_000 },
    { marca: "Fundación", marca_id: "fundacion", visualizaciones: 5_300_000 },
  ];
  const vistas = cuentas.reduce((s, c) => s + c.visualizaciones, 0);
  const base = entradasMarca({
    ...PERFILES.unotv,
    marca: "Todas las marcas",
    vistas,
    alcance: 74_300_000,
    interacciones: 3_910_000,
    engagement: 2.71,
    piezas: 1_980,
    seguidoresInicio: 27_200_000,
    seguidoresFin: 27_940_000,
  });
  // Inyecta las cuentas en el reporte y un desglose por marca×red para el modo "todas".
  const conCuentas = base.map((e) =>
    String(e[0][1]) === "reporte"
      ? ([e[0], { ...(e[1] as object), cuentas }] as Entrada)
      : e,
  );
  return conCuentas;
}

export interface MuestraInforme {
  ctx: { marca: string; red: string; formato: string; periodo: string; marcaId?: string };
  entradas: Entrada[];
}

export const MUESTRAS: Record<string, MuestraInforme> = {
  unotv: {
    ctx: { marca: "UnoTV", red: "todas", formato: "todos", periodo: "junio 2026", marcaId: "unotv" },
    entradas: entradasMarca(PERFILES.unotv),
  },
  "claro-sports": {
    ctx: {
      marca: "Claro Sports",
      red: "todas",
      formato: "todos",
      periodo: "junio 2026",
      marcaId: "claro-sports",
    },
    entradas: entradasMarca(PERFILES["claro-sports"]),
  },
  "nacion-gamer": {
    ctx: { marca: "Nación Gamer", red: "todas", formato: "todos", periodo: "junio 2026", marcaId: "nacion-gamer" },
    entradas: entradasMarca(PERFILES["nacion-gamer"]),
  },
  "piso-15": {
    ctx: { marca: "Piso 15", red: "todas", formato: "todos", periodo: "junio 2026", marcaId: "piso-15" },
    entradas: entradasMarca(PERFILES["piso-15"]),
  },
  fundacion: {
    ctx: { marca: "Fundación", red: "todas", formato: "todos", periodo: "junio 2026", marcaId: "fundacion" },
    entradas: entradasMarca(PERFILES.fundacion),
  },
  todas: {
    ctx: { marca: "Todas las marcas", red: "todas", formato: "todos", periodo: "junio 2026" },
    entradas: entradasTodas(),
  },
};
