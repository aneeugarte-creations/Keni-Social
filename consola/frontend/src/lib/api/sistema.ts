// Fragmento del cliente API: dominio «sistema». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  RespuestaBackups,
  RespuestaBarrerDaemon,
  RespuestaBorrarLoteS3,
  RespuestaBorrarS3,
  RespuestaDaemons,
  RespuestaDoctor,
  RespuestaProbarS3,
  RespuestaRecursos,
  RespuestaRendimiento,
  RespuestaS3,
  RespuestaS3Objetos,
} from "@/types";

export const apiSistema = {
  // --- Estado (el «doctor»: autodiagnóstico de máquina + infra) ---
  estado: (signal?: AbortSignal) => peticion<RespuestaDoctor>("/estado", { signal }),

  // --- Sistema (panel de admin; 403 si no) ---
  sistemaRecursos: (signal?: AbortSignal) =>
    peticion<RespuestaRecursos>("/sistema/recursos", { signal }),
  sistemaDaemons: (signal?: AbortSignal) =>
    peticion<RespuestaDaemons>("/sistema/daemons", { signal }),
  sistemaDaemonBarrer: (daemon: string) =>
    peticion<RespuestaBarrerDaemon>(
      `/sistema/daemons/${encodeURIComponent(daemon)}/barrer`,
      { metodo: "POST" },
    ),
  sistemaBackups: (signal?: AbortSignal) =>
    peticion<RespuestaBackups>("/sistema/backups", { signal }),
  sistemaRendimiento: (signal?: AbortSignal) =>
    peticion<RespuestaRendimiento>("/sistema/rendimiento", { signal }),
  sistemaS3: (signal?: AbortSignal) => peticion<RespuestaS3>("/sistema/s3", { signal }),
  probarS3: () => peticion<RespuestaProbarS3>("/sistema/s3/probar", { metodo: "POST" }),
  s3Objetos: (prefijo?: string, signal?: AbortSignal) =>
    peticion<RespuestaS3Objetos>(
      `/sistema/s3/objetos${query({ prefijo: prefijo || "" })}`,
      { signal },
    ),
  borrarObjetoS3: (key: string) =>
    peticion<RespuestaBorrarS3>("/sistema/s3/borrar", {
      metodo: "POST",
      json: { key },
    }),
  borrarObjetosS3: (keys: string[]) =>
    peticion<RespuestaBorrarLoteS3>("/sistema/s3/borrar-lote", {
      metodo: "POST",
      json: { keys },
    }),

};
