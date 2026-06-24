import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import * as React from "react";

import { api } from "@/lib/api";

/**
 * Ventana de RETORNO del OAuth. Es la `redirect_url` que se pasa al iniciar la
 * conexión: la red oficial (Instagram, Facebook…) o Google redirige aquí al terminar.
 * Avisa al panel que la abrió (`postMessage`) para que refresque al instante y se cierra
 * sola. No menciona ningún proveedor técnico: el equipo solo ve Keni y el servicio.
 *
 * Dos modos según la query:
 *  - Sin `code`: la red ya canjeó por su lado (caso Postproxy). Solo avisa y cierra.
 *  - Con `code` + `state`: el canje lo hace nuestro front (caso Google Analytics);
 *    la cookie de sesión admin viaja en este popup. Avisa según el resultado.
 *
 * Vive fuera del AppShell (sin sidebar): es una ventana emergente efímera.
 */
export default function OauthConectado() {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const state = params.get("state");
  const errorQuery = params.has("error") || params.get("success") === "false";
  // Hay que canjear si Google nos devolvió un código (y no hubo error en la query).
  const debeCanjear = !errorQuery && !!code && !!state;

  const [estado, setEstado] = React.useState<"cargando" | "ok" | "error">(
    debeCanjear ? "cargando" : errorQuery ? "error" : "ok",
  );

  React.useEffect(() => {
    let activo = true;

    function avisar(ok: boolean) {
      try {
        window.opener?.postMessage(
          { tipo: "keni-oauth-conectado", ok },
          window.location.origin,
        );
      } catch {
        // El panel también refresca al recuperar el foco; el mensaje es el camino rápido.
      }
    }

    async function resolver() {
      if (debeCanjear) {
        try {
          const res = await api.canjearGoogleAnalytics({ state: state!, code: code! });
          if (!activo) return;
          const ok = res.conectado;
          setEstado(ok ? "ok" : "error");
          avisar(ok);
        } catch {
          if (!activo) return;
          setEstado("error");
          avisar(false);
        }
      } else {
        avisar(!errorQuery);
      }
    }
    void resolver();
    return () => {
      activo = false;
    };
  }, [debeCanjear, code, state, errorQuery]);

  // Cierra sola una vez resuelto (más despacio si hubo error, para que se lea).
  React.useEffect(() => {
    if (estado === "cargando") return;
    const t = window.setTimeout(
      () => {
        try {
          window.close();
        } catch {
          // Si el navegador no deja cerrar la pestaña, el texto invita a cerrarla a mano.
        }
      },
      estado === "error" ? 4000 : 1500,
    );
    return () => window.clearTimeout(t);
  }, [estado]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center">
      {estado === "cargando" ? (
        <Loader2 className="h-10 w-10 animate-spin text-muted-foreground" aria-hidden="true" />
      ) : estado === "error" ? (
        <XCircle className="h-10 w-10 text-destructive" aria-hidden="true" />
      ) : (
        <CheckCircle2 className="h-10 w-10 text-emerald-500" aria-hidden="true" />
      )}
      <p className="text-lg font-medium">
        {estado === "cargando"
          ? "Conectando…"
          : estado === "error"
            ? "No se pudo conectar la cuenta"
            : "Cuenta conectada"}
      </p>
      <p className="max-w-sm text-sm text-muted-foreground">
        {estado === "cargando"
          ? "Un momento, estamos terminando la conexión."
          : estado === "error"
            ? "Vuelve a Keni e inténtalo de nuevo. Puedes cerrar esta ventana."
            : "Ya puedes cerrar esta ventana y volver a Keni."}
      </p>
    </div>
  );
}
