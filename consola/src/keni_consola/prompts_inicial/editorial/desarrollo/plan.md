---
titulo: "Plan · diseñar el cambio"
descripcion: "Cómo planear un cambio en keni-social: acotar el alcance, identificar seams y consumidores, y decidir qué tests se tocan ANTES de escribir código."
tipo: editorial
clase: desarrollo
marcas: []
pipelines: []
creado: 2026-06-18T00:00:00+00:00
actualizado: 2026-06-18T00:00:00+00:00
---

# Plan · diseñar antes de implementar

Entras con el mapa de la fase `analyze`. Sales con una lista de cambios concretos, archivo por archivo, incluyendo sus tests. No empieces a editar hasta tener esto.

## Acota el alcance

- Resuelve EXACTAMENTE lo pedido. No hagas gold-plating ni refactors oportunistas que ensucien el diff.
- Si el cambio es grande, pártelo en pasos pequeños y coherentes (idealmente un commit por foto/cambio lógico).
- Decide la VERDAD: si un test afirma una forma vieja que vas a cambiar, decide cuál es la forma correcta y arregla el lado correcto; no fuerces el producto a un test caduco ni al revés.

## Identifica cada seam que cruzas

Un seam es una frontera donde dos lados deben moverse juntos. Para cada uno, anota el OTRO lado y planéalo en el MISMO commit:

- **Fachada de reexport** (`keni_consola.marcas` reexporta `keni_shared.marcas`, y otras): si añades un símbolo a la fuente (`keni_shared`) y lo llamas vía la fachada, añádelo al `from … import (…)` Y al `__all__` de la fachada. `grep -rn "marcas\.<nombre>"` para ver quién lo consume.
- **Router nuevo**: los routers bajo `api/` y `api/sistema/` se AUTODESCUBREN. Un router top-level nuevo se declara en su `apps/<app>.toml` (`modulos_backend`). Si importa de otra app es un CRUCE: enrútalo por keni-shared/gateway o justifícalo en `SEAMS_PERMITIDOS` (ADR 0005 §Seams). Nota: declarar el `.toml` o tocar `app.py`/`api/__init__.py` puede ser propiedad del orquestador; si lo es, déjalo en tu informe en vez de editarlo.
- **Forma observable** (firma de API, FORMA de una respuesta, esquema/constraint de BD, etapa de un daemon, contrato de salida de un prompt): `grep` los tests que afirman la forma vieja y márcalos para actualizar.
- **Infra compartida** (cola de jobs, allowlist de truncado en `tests/_postgres.py`, migraciones): propaga a todos los consumidores.

## Tablas y migraciones

- Patrón de tabla nueva: copia uno existente de extremo a extremo (p. ej. `evergreen_ideas`): módulo `db_*.py`, repos, reexport en el barrel `db.py`, y registro de la migración en `migracion.py` + `_db_core/migraciones*.py`. Si el registro de migración o el barrel es propiedad del orquestador, deja el fragmento exacto en tu informe.

## Lista de salida

Para cada archivo: qué cambias y por qué. Marca explícitamente:
- Archivos de PRODUCTO que editas.
- Archivos de TEST que tocas en el mismo commit (cambio de comportamiento = cambio de tests).
- Archivos de INTEGRACIÓN/propiedad de otro que NO editas: deja el fragmento exacto para el informe.

Si no puedes nombrar los tests que cambiarán, aún no entiendes el cambio: vuelve a `analyze`.
