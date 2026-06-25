/**
 * Datos de muestra para la vista previa del Informe (deck PDF de Métricas). Construye las
 * ENTRADAS crudas con la MISMA forma que el backend (los pares [queryKey, data] que alimentan
 * `desdeEntradas` en producción), para ver el deck real con cifras plausibles y deterministas.
 * No toca red ni backend; solo sirve para iterar el diseño en localhost.
 *
 * Las cifras RECONCILIAN entre láminas igual que lo haría el backend real: la serie diaria suma
 * al total del mes, el desglose por red suma a las interacciones, el engagement = interacciones /
 * visualizaciones, y los seguidores son una serie diaria acumulada (no una recta).
 */

type Entrada = [readonly unknown[], unknown];

/** Día ISO del periodo de muestra (junio 2026). */
function iso(dia: number): string {
  return `2026-06-${String(dia).padStart(2, "0")}`;
}

/**
 * Escala una serie de pesos a enteros que suman EXACTAMENTE `objetivo` (reparte el resto de
 * redondeo en los mayores). Garantiza que las partes cuadren con el total mostrado en otra lámina.
 */
function escalarASuma(pesos: number[], objetivo: number): number[] {
  const suma = pesos.reduce((a, b) => a + b, 0) || 1;
  const out = pesos.map((p) => Math.round((p / suma) * objetivo));
  let resto = objetivo - out.reduce((a, b) => a + b, 0);
  const orden = out.map((_, i) => i).sort((a, b) => out[b] - out[a]);
  let k = 0;
  while (resto !== 0 && orden.length) {
    const i = orden[k % orden.length];
    const paso = resto > 0 ? 1 : -1;
    if (out[i] + paso >= 0) {
      out[i] += paso;
      resto -= paso;
    }
    k++;
  }
  return out;
}

/** Reparto de visualizaciones por red (pesos fijos), escalado para sumar EXACTAMENTE `vistas`. */
const PESOS_VISTAS: Record<string, number> = {
  facebook: 0.34,
  tiktok: 0.29,
  instagram: 0.2,
  youtube: 0.11,
  x: 0.06,
};
/** Interacción por vista RELATIVA por red (%): TikTok/Instagram enganchan más que Facebook. */
const TASA_ENG: Record<string, number> = {
  facebook: 1.8,
  tiktok: 4.7,
  instagram: 3.8,
  youtube: 2.2,
  x: 3.1,
};
/** Mezcla de tipos de interacción (suma 1): me gusta domina; compartir+guardar = alto valor. */
const MEZCLA = { likes: 0.74, comentarios: 0.09, compartidos: 0.12, guardados: 0.05 };
const REDES = Object.keys(PESOS_VISTAS);

function repartoRedes(vistas: number): Array<{ red: string; visualizaciones: number }> {
  const valores = escalarASuma(
    REDES.map((r) => PESOS_VISTAS[r]),
    vistas,
  );
  return REDES.map((red, i) => ({ red, visualizaciones: valores[i] }));
}

/** Forma de onda diaria (n días) con un pico marcado el día `spikeDia`; pesos sin escalar. */
function ondaDiaria(n: number, spikeDia: number, spikeMult: number): number[] {
  return Array.from({ length: n }, (_, i) => {
    const onda = Math.sin((i / n) * Math.PI * 3);
    const base = 1 + 0.32 * onda + 0.5 * (i / n);
    return i + 1 === spikeDia ? base * spikeMult : base;
  });
}

interface PerfilMarca {
  id: string;
  marca: string;
  vistas: number;
  alcance: number;
  /** Engagement objetivo (%); las interacciones se derivan para que cuadre con vistas. */
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
    engagement: 3.1,
    piezas: 642,
    seguidoresInicio: 8_420_000,
    seguidoresFin: 8_612_000,
  },
  "claro-sports": {
    id: "claro-sports",
    marca: "Claro Sports",
    vistas: 35_600_000,
    alcance: 22_900_000,
    engagement: 3.2,
    piezas: 488,
    seguidoresInicio: 6_120_000,
    seguidoresFin: 6_268_000,
  },
  "nacion-gamer": {
    id: "nacion-gamer",
    marca: "Nación Gamer",
    vistas: 15_400_000,
    alcance: 9_800_000,
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
    { titulo: "Checo Pérez firma un Gran Premio para el olvido", plataforma: "facebook", dia: 19 },
    { titulo: "Entrevista exclusiva con el técnico tras la victoria", plataforma: "youtube", dia: 11 },
    { titulo: "Las mejores jugadas de la jornada en 60 segundos", plataforma: "tiktok", dia: 23 },
    { titulo: "Tabla de posiciones: así marcha la Liga MX", plataforma: "x", dia: 5 },
    { titulo: "Resumen NBA: la final que paralizó la madrugada", plataforma: "instagram", dia: 25 },
    { titulo: "Fichaje confirmado: llega refuerzo de Europa", plataforma: "facebook", dia: 2 },
  ],
  "nacion-gamer": [
    { titulo: "Reseña: el RPG del año llega por fin a consolas", plataforma: "tiktok", dia: 16 },
    { titulo: "Filtran el roster completo del próximo shooter competitivo", plataforma: "instagram", dia: 8 },
    { titulo: "Guía: cómo subir de rango antes del cierre de temporada", plataforma: "youtube", dia: 21 },
    { titulo: "Nintendo anuncia un Direct sorpresa para esta semana", plataforma: "facebook", dia: 5 },
    { titulo: "Los 5 indies mexicanos que tienes que jugar ya", plataforma: "tiktok", dia: 24 },
    { titulo: "Torneo nacional de esports: así quedó la gran final", plataforma: "x", dia: 12 },
    { titulo: "Análisis: ¿vale la pena la nueva expansión?", plataforma: "instagram", dia: 27 },
    { titulo: "PC contra consola: el debate que nunca termina", plataforma: "facebook", dia: 2 },
  ],
  "piso-15": [
    { titulo: "Exclusiva: la boda secreta que paralizó las redes", plataforma: "instagram", dia: 14 },
    { titulo: "VIDEO: el reencuentro en vivo que nadie esperaba", plataforma: "tiktok", dia: 9 },
    { titulo: "Top 10 de los estrenos de la semana en streaming", plataforma: "youtube", dia: 19 },
    { titulo: "La entrevista más sincera del año, sin filtros", plataforma: "facebook", dia: 6 },
    { titulo: "Detrás de cámaras del concierto del momento", plataforma: "instagram", dia: 23 },
    { titulo: "Polémica: las declaraciones que dividen opiniones", plataforma: "x", dia: 11 },
    { titulo: "Así reaccionaron los famosos al gran anuncio", plataforma: "tiktok", dia: 26 },
    { titulo: "Lo mejor de la alfombra roja en 60 segundos", plataforma: "facebook", dia: 3 },
  ],
  fundacion: [
    { titulo: "Entregamos 10 mil becas a jóvenes de todo México", plataforma: "facebook", dia: 17 },
    { titulo: "VIDEO: la historia de superación que hoy inspira a todo el país", plataforma: "tiktok", dia: 10 },
    { titulo: "Inauguramos un nuevo centro de salud comunitario", plataforma: "instagram", dia: 7 },
    { titulo: "Voluntarios reforestan más de 5 mil hectáreas", plataforma: "youtube", dia: 20 },
    { titulo: "El programa de empleo que cambia vidas en zonas rurales", plataforma: "facebook", dia: 25 },
    { titulo: "Donativos récord para damnificados por las lluvias", plataforma: "x", dia: 13 },
    { titulo: "Niños reciben equipo de cómputo en escuelas rurales", plataforma: "instagram", dia: 28 },
    { titulo: "Jornada de salud visual atiende a miles de familias", plataforma: "tiktok", dia: 4 },
  ],
};

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

  // Reparto de vistas por red (suma exacta = p.vistas).
  const porRed = repartoRedes(p.vistas);
  const vistasPorRed = new Map(porRed.map((r) => [r.red, r.visualizaciones]));

  // Interacciones por red = vistasRed × tasa(red), escaladas para que el engagement global = objetivo.
  // Engagement medio "natural" (% interacción/vista ponderado por vistas) y factor para llevarlo
  // al engagement objetivo de la marca sin perder la forma relativa entre redes.
  const tasaMediaPond =
    REDES.reduce((s, r) => s + (vistasPorRed.get(r) ?? 0) * TASA_ENG[r], 0) / Math.max(1, p.vistas);
  const factor = p.engagement / tasaMediaPond;
  const interPorRed = new Map(
    REDES.map((r) => [r, Math.round((vistasPorRed.get(r) ?? 0) * (TASA_ENG[r] * factor) / 100)]),
  );
  const interaccionesTotal = REDES.reduce((s, r) => s + (interPorRed.get(r) ?? 0), 0);
  const engagement = Math.round((interaccionesTotal / p.vistas) * 1000) / 10;

  // Desglose por red×tipo: cada red reparte sus interacciones en los 4 tipos (suma exacta).
  const celdas = REDES.map((red) => {
    const inter = interPorRed.get(red) ?? 0;
    const [likes, comentarios, compartidos, guardados] = escalarASuma(
      [MEZCLA.likes, MEZCLA.comentarios, MEZCLA.compartidos, MEZCLA.guardados],
      inter,
    );
    return { marca: p.marca, red, likes, comentarios, compartidos, guardados };
  });

  // Tendencia diaria: la serie de vistas suma EXACTAMENTE p.vistas; la de interacciones, el total.
  const vistasDia = escalarASuma(ondaDiaria(n, 18, 3.0), p.vistas);
  const interDia = escalarASuma(ondaDiaria(n, 18, 2.6), interaccionesTotal);
  const tendencia = {
    puntos: Array.from({ length: n }, (_, i) => ({
      fecha: iso(i + 1),
      visualizaciones: vistasDia[i],
      interacciones: interDia[i],
    })),
  };

  // Seguidores: ganancia diaria con micro-variación (curva real acumulada, no una recta).
  const neto = p.seguidoresFin - p.seguidoresInicio;
  const ganancias = escalarASuma(
    Array.from({ length: n - 1 }, (_, i) => 1 + 0.45 * Math.sin((i / (n - 1)) * Math.PI * 2) + 0.25 * Math.sin((i / (n - 1)) * Math.PI * 5)),
    neto,
  );
  const totalesSeg: number[] = [p.seguidoresInicio];
  for (const g of ganancias) totalesSeg.push(totalesSeg[totalesSeg.length - 1] + g);
  const seguidores = {
    puntos: totalesSeg.map((total, i) => ({ fecha: iso(i + 1), total })),
  };

  const top = (TITULARES[p.id] ?? []).map((t, i) => {
    const vistas = Math.round(p.vistas * (0.051 - i * 0.004));
    const engagementPieza = Number((4.6 - i * 0.32).toFixed(1));
    return {
      titulo: t.titulo,
      plataforma: t.plataforma,
      publicado: `${String(t.dia).padStart(2, "0")} jun`,
      visualizaciones: vistas,
      interacciones: Math.round((vistas * engagementPieza) / 100),
      engagement_pct: engagementPieza,
      url: urlMuestra(p.id, t.plataforma, i),
      formato: formatoMuestra(t.plataforma),
    };
  });

  const reporte = {
    total: {
      visualizaciones: p.vistas,
      alcance: p.alcance,
      interacciones: interaccionesTotal,
      engagement_pct: engagement,
      piezas: p.piezas,
    },
    por_red: porRed,
  };

  // El delta de engagement se DERIVA de los de vistas e interacciones (engagement = inter / vistas),
  // para que las cuatro variaciones cuadren entre sí: eng_antes = eng × (1+visΔ)/(1+interΔ).
  const visVar = 14.2;
  const interVar = -3.4;
  const engDif =
    Math.round(engagement * (1 - (1 + visVar / 100) / (1 + interVar / 100)) * 10) / 10;
  const comparar = {
    total: {
      metricas: [
        { metrica: "visualizaciones", variacion_pct: visVar },
        { metrica: "alcance", variacion_pct: 5.1 },
        { metrica: "interacciones", variacion_pct: interVar },
        { metrica: "engagement_pct", diferencia: engDif },
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
    id: "unotv",
    marca: "Todas las marcas",
    vistas,
    alcance: 74_300_000,
    engagement: 3.0,
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
