# Roadmap de UX/UI de keni-social

*Evaluación heurística de la experiencia para el community manager NO técnico. Nació como una
foto fija read-only de toda la superficie; **la Ola 1 de mejoras ya se implementó** (ver abajo),
así que este doc se mantiene por su **rationale de diseño durable** (el "norte" de experiencia,
§3) y las **recomendaciones todavía abiertas** (§2).*

**Audiencia del producto:** community managers NO técnicos de AMX (UnoTV, Claro Sports,
Nación Gamer, Piso 15, Fundación) + su jefe Bernardo.
**Filosofía:** la IA produce y verifica; el humano aprueba.

---

## 0. Qué ya se hizo (Ola 1 — enviada)

Las recomendaciones de mayor impacto/menor esfuerzo de la primera evaluación **ya están en el
código** (verificado leyéndolo):

- **Semáforo de veredicto + leyenda al INICIO de cada skill de copy.** `copy-desde-nota`,
  `clip-a-copy`, etc. abren con un bloque "veredicto + leyenda, antes del copy" (`🟢/🟡/🔴` con
  su explicación); el checklist detallado se mantiene al final. (Ver `*/SKILL.md`, sección "Cómo
  ABRE tu salida".)
- **Picos resumidos en CLI/notificaciones:** `picos.render_markdown` encabeza con el top-N y
  colapsa el resto en una línea (ya no es un muro de 24–29 alertas planas).
- **Doctor accionable:** agrupa las credenciales en una sola línea
  (`Credenciales: K/N plataformas conectadas`) y cierra con el siguiente paso
  (`python -m keni_metricas.asistente`).
- **Nombres de marca legibles**, fecha es-MX en el reporte, y picos colapsados en el dashboard.

Lo que sigue es lo **todavía abierto** y el rationale que no caduca.

---

## 2. Recomendaciones todavía abiertas (Olas 2–3)

Esfuerzo: **S** (≤ medio día) · **M** (1–2 días) · **L** (3+ días o requiere diseño).
Impacto: en el usuario no técnico (CM) y en Bernardo. (La Ola 1 ya se envió — ver §0.)

| # | Mejora | Superficie / archivo | Impacto | Esfuerzo | Ola |
|---|---|---|---|---|---|
| 8 | "Empieza aquí en 10 min": un único quick-start para el CM que enlaza doctor como paso 1 | `README.md`, `docs/` | Alto | M | 2 |
| 9 | Dashboard: exportable a PDF/impresión (`@media print`) + documentar `--presentacion` | `dashboard.py`, guía | Medio | M | 2 |
| 10 | Callout "lo que rompió": aclarar criterio (engagement %) o ponderar por volumen | `dashboard.py` | Medio | M | 2 |
| 11 | Loop de vuelta a la acción: dashboard/reporte sugieren "pide copy para X que es lo que rinde" | `dashboard.py`, `reporte.py` | Medio | M | 2 |
| 12 | Tarjeta de referencia ✅/⚠️/❌ + sección de métricas (dashboard/doctor) en la guía del CM | `docs/guia-community-manager.md` | Medio | S | 2 |
| 13 | Guía de credenciales menos técnica: "no lo tengo → vacío y pídeselo a tu admin" por bloque | `asistente.py` | Medio | S | 2 |
| 14 | Conteo de caracteres con indicador visual estandarizado (cabe/no cabe) garantizado por producto | `plataformas.md`, `contar.py` | Bajo | M | 3 |
| 15 | Estados vacíos del dashboard (marca sin datos / cobertura 0) diseñados explícitamente | `dashboard.py` | Bajo | M | 3 |
| 16 | Selección de marca asistida (lista en vez de id memorizado) para invocar skills | comandos `/`, skills | Alto | L | 3 |
| 17 | Reconciliar marcas declaradas en el asistente con la fuente activa (avisar si `muestra`) | `asistente.py`, `doctor.py` | Medio | M | 3 |

(Se conservan los números originales para no perder la traza; las filas 1–7 eran la Ola 1, ya
enviada.)

---

## 3. El "norte" de experiencia (principios UX del producto)

Estos principios deben guiar cualquier decisión de rediseño. Derivan de la filosofía
"la IA produce y verifica, el humano aprueba" y de la audiencia (CM no técnico + Bernardo).

1. **El veredicto primero.** Lo más accionable —¿puedo aprobar esto? ¿qué miro hoy?— va arriba
   y en una línea. El detalle viene después, para quien quiera profundizar. Nadie debería hacer
   scroll para saber si una pieza está lista.

2. **Confianza calibrada y visible.** Todo lo que la IA produce dice **cuándo creerle**:
   ✅ confía, ⚠️ confírmalo tú, ❌ hay un problema. La leyenda viaja con la salida, no vive solo
   en un doc. El producto enseña al CM a ser el aprobador, no a delegar a ciegas.

3. **Una sola voz, una sola ortografía.** Una marca se escribe igual en todas las superficies.
   El mismo concepto (engagement, alcance, "lo que rompió") se nombra y formatea igual en skill,
   CLI, dashboard y guía. La consistencia es lo que hace que un no técnico confíe en el sistema.

4. **Español de México, siempre.** Fechas (24 may 2026), separadores de miles, tono. Cero ISO
   crudo, cero jerga de prensa española, cero inglés técnico filtrándose a la cara del usuario.

5. **Señal sobre ruido.** Lo importante es poco y destaca; lo demás se colapsa o se resume.
   24 alertas iguales no son información: 3 que importan + "ver todas" sí lo son.

6. **Seguro por defecto, y que se note.** Dry-run y "nada se ha publicado/enviado" no son letra
   pequeña: son una promesa visible que reduce el miedo del CM a "romper algo". El humano siempre
   tiene el último clic.

7. **Cada pantalla termina con el siguiente paso, y el loop se cierra solo.** Diagnosticar sin
   decir qué hacer es dejar al no técnico a medias. El doctor, el asistente y el dashboard cierran
   señalando la acción siguiente, cerrando el loop hacia "produce → verifica → aprueba → publica →
   mide → vuelve a producir". Y donde antes el humano lanzaba **cada** paso a mano, la **lista viva
   multi-fuente** (calendario, RSS, radar) ahora **auto-genera** el borrador al entrar un tema y lo
   deja en la cola de revisión; el humano valida **checkpoints** (aprobar el copy, autorizar la
   publicación) en vez de operar cada eslabón. El principio se mantiene —el siguiente paso siempre
   está a la vista—, pero el sistema adelanta el trabajo operativo hasta el punto de validación, y
   la publicación queda **programada** tras la aprobación. (Ver nota al cierre.)

8. **Onboarding por tareas, no por arquitectura.** El CM aprende "cómo saco copy de una nota",
   no "qué es un MCP". La `guia-community-manager.md` es el patrón: replicarlo en todo el
   material de cara al usuario.

---

*Evaluación heurística de UX. La Ola 1 (las 5 mejoras top de la primera versión: semáforo de
veredicto al inicio, nombres de marca legibles, resumen de picos, doctor y asistente accionables)
**ya se implementó** y por eso se resumió arriba en §0 en vez de mantener el detalle de
implementación. El "norte" de experiencia (§3) es el rationale durable que debe guiar cualquier
rediseño; las olas 2–3 (§2) recogen lo que sigue abierto por orden de impacto/esfuerzo.*

> **Nota — cierre de loop hacia auto-generación (principio 7).** El paso de "asistente que el
> humano dispara paso a paso" a "lista viva que adelanta el trabajo hasta el checkpoint" está
> evaluado, diseñado y parcialmente construido (H1–H5) en
> [`contexto/2026-05-31-lista-viva-angel.md`](contexto/2026-05-31-lista-viva-angel.md): importador
> de calendario (H1), auto-generación de copy al entrar un tema (H2, gated OFF por defecto), score
> de prioridad dinámico (H3) y Panel-9am como lista curada del día (H5). El humano sigue teniendo
> el último clic; lo que cambia es que el sistema llega más lejos antes de pedírselo.
