import type { RespuestaCatalogo } from "@/types/catalogo";
import type { UsoCuenta } from "@/hooks/use-uso-cuenta";

/** Navegación de muestra: los mismos 5 bloques/12 ítems de producción, sin pasar por el backend. */
export const CATALOGO_MUESTRA: RespuestaCatalogo = {
  apps: [],
  navegacion: [
    {
      etiqueta: "Operación",
      items: [
        { ruta: "/operacion/investigacion", etiqueta: "Investigación", icono: "Search", descripcion: "Curación de noticias" },
        { ruta: "/operacion/feed", etiqueta: "Feed", icono: "LayoutGrid", descripcion: "Ideación de piezas" },
        { ruta: "/operacion/programa", etiqueta: "Programa", icono: "CalendarDays", descripcion: "Calendario de publicación" },
      ],
    },
    {
      etiqueta: "Equipo",
      items: [
        { ruta: "/operacion/trabajo", etiqueta: "Trabajo", icono: "ClipboardList", descripcion: "Eventos y tareas del equipo" },
        { ruta: "/operacion/turnos", etiqueta: "Calendario", icono: "CalendarClock", descripcion: "Horario de turnos" },
      ],
    },
    {
      etiqueta: "Publicación",
      items: [
        { ruta: "/contenido/imagen", etiqueta: "Imagen", icono: "Image", descripcion: "Editor de imagen" },
        { ruta: "/contenido/video", etiqueta: "Video", icono: "Clapperboard", descripcion: "Editor de video" },
        { ruta: "/contenido/audio", etiqueta: "Audio", icono: "AudioLines", descripcion: "Editor de audio" },
        { ruta: "/contenido/galeria", etiqueta: "Galería", icono: "Camera", descripcion: "Plantillas y piezas" },
      ],
    },
    {
      etiqueta: "Máquina",
      items: [
        { ruta: "/contexto", etiqueta: "Contexto", icono: "Layers", descripcion: "Biblioteca editorial" },
        { ruta: "/agentes", etiqueta: "Agentes", icono: "Bot", descripcion: "Cómputo y economía" },
      ],
    },
    {
      etiqueta: "Datos",
      items: [{ ruta: "/metricas", etiqueta: "Analíticas", icono: "BarChart3", descripcion: "Métricas por red" }],
    },
  ],
};

/** Uso de cuenta de muestra: Semana al 100% (alerta), igual al caso que reportó el humano. */
export const USO_MUESTRA: UsoCuenta[] = [
  {
    cuenta: "a",
    etiqueta: "Claro Sports",
    marcas: ["claro-sports"],
    conectada: true,
    semana_pct: 100,
    sesion_5h_pct: 0,
    sonnet_pct: null,
    reset_semana_iso: "2026-07-04T00:00:00Z",
    reset_semana_txt: "4 jul a las 00:00",
    reset_sesion_iso: null,
    actualizado_ts: 1_751_360_000,
    al_100: true,
    alerta_roja: true,
    dia: { consumo_pct: 64, umbral_pct: 100, limite: "semanal", pausado: false },
  },
];
