# ADR 0010 — Economía de la generación

La generación corre `claude -p` con la misma suscripción que el equipo usa a diario. Una
ráfaga de trabajo de fondo (pipeline/autogen) podría agotar el cupo de todos —humanos
incluidos— sin que nadie lo vea venir. La economía de la generación es el guardián que lo
impide, gobernando el consumo en capas visibles y editables en caliente.

## Principios

- **Ledger compartido.** Cada generación cerrada deja su gasto (tokens in/out, coste,
  prompt) en una cuenta única en Postgres, idempotente por generación. Es la única cuenta
  compartida entre procesos (back/worker/daemons) y se autolibera al rotar el día UTC. Lo
  escribe un hook en el punto único de cierre, así cubre todos los caminos sin tocar cada
  lanzador. Quien no consume tokens medibles (imagen, render) no deja fila.

- **Corte automático gradual.** Al rebasar el presupuesto diario, primero cede el fondo y
  lo manual del equipo sigue; al rebasar el presupuesto más un margen, el corte es total.
  El gate vive en dos puntos: admisión (encolar, que degrada con un 429 claro) y reclamo
  (el worker deja de tomar trabajo). La ráfaga ya encolada también se corta: queda
  pendiente, no se pierde. Lo encolado se reanuda solo al rotar el día.

- **Kill switch humano.** Una parada manda sobre todo: no se encola ni se reclama nada; lo
  que corre termina y lo encolado espera. Es el freno de mano de un clic.

- **No cortar ante un parpadeo de la BD.** El presupuesto es guardián de economía, no
  cinturón funcional: ante un fallo de lectura se sirve el último valor conocido y la
  máquina sigue. Un falso corte pararía todo por un blip.

- **Tope de intentos.** Un job que agota sus intentos se descarta con error claro en vez de
  re-reclamarse para siempre quemando tokens en cada vuelta.

- **Economía de contexto.** Un tope duro del tamaño del prompt lo rechaza antes de gastar,
  con remedio en el mensaje; un umbral de aviso avisa antes del tope. El tamaño se mide por
  generación y por día en el ledger.

- **Defecto inocuo.** Sin presupuesto fijado, la economía está apagada y el comportamiento
  no cambia; se enciende fijando el presupuesto desde el Monitor.

El presupuesto, el margen, los topes y la parada se editan en caliente y el estado del día
(nivel, gastado, restante, proyección) es visible para el Monitor y los agentes. El alcance
del corte —global, por motor de la máquina o por marca— sigue al ámbito del presupuesto
fijado, tomando siempre el control más restrictivo entre los que apliquen.
