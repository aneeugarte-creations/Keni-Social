import { CheckCircle2, XCircle } from "lucide-react";
import * as React from "react";

/**
 * Ventana de RETORNO del OAuth de una red. Es la `redirect_url` que se pasa al iniciar
 * la conexión: la red oficial (Instagram, Facebook…) redirige aquí al terminar. Avisa
 * al panel de Marcas que la abrió (`postMessage`) para que refresque al instante y se
 * cierra sola. No menciona ningún proveedor: el equipo solo ve Keni y la red.
 *
 * Vive fuera del AppShell (sin sidebar): es una ventana emergente efímera.
 */
export default function OauthConectado() {
  const params = new URLSearchParams(window.location.search);
  const hayError = params.has("error") || params.get("success") === "false";

  React.useEffect(() => {
    try {
      window.opener?.postMessage(
        { tipo: "keni-oauth-conectado", ok: !hayError },
        window.location.origin,
      );
    } catch {
      // El panel también refresca al recuperar el foco; el mensaje es el camino rápido.
    }
    const t = window.setTimeout(() => {
      try {
        window.close();
      } catch {
        // Si el navegador no deja cerrar la pestaña, el texto invita a cerrarla a mano.
      }
    }, hayError ? 4000 : 1500);
    return () => window.clearTimeout(t);
  }, [hayError]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 p-6 text-center">
      {hayError ? (
        <XCircle className="h-10 w-10 text-destructive" aria-hidden="true" />
      ) : (
        <CheckCircle2 className="h-10 w-10 text-emerald-500" aria-hidden="true" />
      )}
      <p className="text-lg font-medium">
        {hayError ? "No se pudo conectar la red" : "Cuenta conectada"}
      </p>
      <p className="max-w-sm text-sm text-muted-foreground">
        {hayError
          ? "Vuelve a Keni e inténtalo de nuevo. Puedes cerrar esta ventana."
          : "Ya puedes cerrar esta ventana y volver a Keni."}
      </p>
    </div>
  );
}
