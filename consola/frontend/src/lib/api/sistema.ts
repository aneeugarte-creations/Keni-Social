// Fragmento del cliente API: dominio «sistema». Generado al partir lib/api.ts.
// El objeto compuesto vive en ./index.ts; aquí solo el fragmento + sus imports.
import { peticion, query } from "./_core";
import type {
  RespuestaBackups,
  RespuestaBarrerDaemon,
  RespuestaBarridosDaemon,
  RespuestaBorrarLoteS3,
  RespuestaBorrarS3,
  RespuestaCuenta,
  RespuestaCuentaAccion,
  RespuestaCuentaMarcas,
  RespuestaDaemons,
  RespuestaDoctor,
  RespuestaGithub,
  RespuestaGithubLoginIniciar,
  RespuestaLoginIniciar,
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
  // Historial de barridos de un daemon (LOG por barrido, nuevo primero). 404 si no existe.
  sistemaDaemonBarridos: (daemon: string, limite?: number, signal?: AbortSignal) =>
    peticion<RespuestaBarridosDaemon>(
      `/sistema/daemons/${encodeURIComponent(daemon)}/barridos${query({
        limite: limite ? String(limite) : undefined,
      })}`,
      { signal },
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

  // --- Cuenta de Claude del servidor (proxy admin al control del daemons) ---
  // Soporta DOS cuentas (`cuenta`: "a"|"b"; def "a"). `cuenta=b` se mapea al config-dir de B
  // (`/data/claude-cfg-b`) en el servidor; "a" deja la ruta intacta (cuenta histórica).
  sistemaCuenta: (cuenta?: "a" | "b", signal?: AbortSignal) =>
    peticion<RespuestaCuenta>(`/sistema/cuenta${query({ cuenta })}`, { signal }),
  cuentaLoginIniciar: (
    opts: { console?: boolean; email?: string; sso?: boolean },
    cuenta?: "a" | "b",
  ) =>
    peticion<RespuestaLoginIniciar>(`/sistema/cuenta/login/iniciar${query({ cuenta })}`, {
      metodo: "POST",
      json: opts,
      // El back lanza `claude auth login` y espera a que imprima la URL: techo amplio
      // (el default de 30 s se queda corto si Anthropic tarda en responder).
      timeoutMs: 120_000,
    }),
  cuentaLoginCodigo: (sesion: string, codigo: string) =>
    peticion<RespuestaCuentaAccion>("/sistema/cuenta/login/codigo", {
      metodo: "POST",
      json: { sesion, codigo },
      // Validar el código contra Anthropic + persistir credenciales puede tardar: techo amplio.
      timeoutMs: 120_000,
    }),
  cuentaLoginCancelar: (sesion: string) =>
    peticion<{ ok: boolean }>("/sistema/cuenta/login/cancelar", {
      metodo: "POST",
      json: { sesion },
    }),
  cuentaLogout: (cuenta?: "a" | "b") =>
    peticion<RespuestaCuentaAccion>(`/sistema/cuenta/logout${query({ cuenta })}`, {
      metodo: "POST",
    }),

  // --- Reparto de marcas por cuenta (admin: qué marca sirve cada cuenta A/B) ---
  cuentaMarcas: (signal?: AbortSignal) =>
    peticion<RespuestaCuentaMarcas>("/sistema/cuenta-marcas", { signal }),
  // `cuenta: ""` limpia el override (vuelve al defecto); 'a'|'b' lo fija.
  asignarCuentaMarca: (datos: { marca: string; cuenta: string }) =>
    peticion<RespuestaCuentaMarcas>("/sistema/cuenta-marcas", {
      metodo: "POST",
      json: datos,
    }),

  // --- Proveedor GitHub del servidor (gh, proxy admin al control del daemons) ---
  githubEstado: (signal?: AbortSignal) =>
    peticion<RespuestaGithub>("/sistema/github", { signal }),
  githubLoginIniciar: () =>
    peticion<RespuestaGithubLoginIniciar>("/sistema/github/login/iniciar", {
      metodo: "POST",
      json: {},
      // El back lanza `gh auth login` y espera a que imprima el código de dispositivo: techo amplio.
      timeoutMs: 120_000,
    }),
  githubLoginConfirmar: (sesion: string) =>
    peticion<RespuestaCuentaAccion>("/sistema/github/login/confirmar", {
      metodo: "POST",
      json: { sesion },
      // `gh` hace polling hasta que el usuario autoriza en GitHub: espera el cierre del proceso.
      timeoutMs: 300_000,
    }),
  githubLoginCancelar: (sesion: string) =>
    peticion<{ ok: boolean }>("/sistema/github/login/cancelar", {
      metodo: "POST",
      json: { sesion },
    }),
  githubLogout: () =>
    peticion<RespuestaCuentaAccion>("/sistema/github/logout", { metodo: "POST" }),
};
