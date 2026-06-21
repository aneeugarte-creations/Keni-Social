# ADR 0013 — Cuenta de Claude gestionable desde el panel

La generación corre `claude -p` con la cuenta de la máquina. Esa cuenta se gestiona
desde el panel (Sistema → Cuenta de Claude), sin SSH ni reinicios.

## Principios

- **Las credenciales viven en el volumen compartido `/data`, no en la imagen.**
  `CLAUDE_CONFIG_DIR=/data/claude-cfg` para `worker` y `daemons` (mismo volumen). Son la
  ÚNICA fuente de la cuenta y persisten a recreaciones de contenedor. La cuenta se fija con
  `claude auth login` desde el panel, no con un secreto del host. `ANTHROPIC_API_KEY` queda
  como alternativa opcional por API key.

- **Cambiar de cuenta aplica en caliente.** Ambos procesos releen las credenciales en cada
  invocación, así que un login nuevo surte efecto sin reiniciar.

- **El listener de control vive en `daemons`, no en el `back`.** Cambiar la cuenta ejecuta
  `claude`, que el `back` no tiene (solo encola). El `daemons` (imagen del worker, con
  `claude`; instancia única) expone un control mínimo en la red interna de Docker, protegido
  por un bearer. El login interactivo mantiene vivo el proceso `claude auth login` en un PTY
  entre peticiones.

- **El `back` proxea, admin-gated, zero-config.** `/api/sistema/cuenta/*` exige sesión admin
  y reenvía al control con el bearer. El bearer back↔daemons se auto-persiste en `/data`,
  creado atómicamente: la sección funciona sin configurar nada. La única acción del operador
  es fijar la cuenta con un login.

- **El medidor de uso (`/usage`) se parsea a campos estructurados** (sesión / semana, con sus
  resets). La identidad de la cuenta (email/org) no la expone el CLI en modo headless: no se
  muestra.
