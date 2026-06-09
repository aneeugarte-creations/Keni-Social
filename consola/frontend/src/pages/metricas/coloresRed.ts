/**
 * Paleta de color por red social, compartida por las visualizaciones de Métricas
 * (Panorama de piezas, Evolución por red, …). Tonos FOSFORITO y máximamente distintos
 * entre sí (rueda de color repartida), legibles sobre fondo claro y oscuro.
 */
export const COLOR_RED: Record<string, string> = {
  facebook: "#00b3ff", // azul eléctrico
  instagram: "#a855f7", // violeta neón
  tiktok: "#00e64d", // verde neón
  youtube: "#ff1f3d", // rojo neón
  x: "#ff8a00", // naranja neón
};

/** Color para redes fuera del catálogo canónico. */
export const COLOR_FALLBACK = "#b026ff"; // violeta neón

/** Color de una red (canónica) con fallback. */
export const colorDe = (red: string): string => COLOR_RED[red] ?? COLOR_FALLBACK;
