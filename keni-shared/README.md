# keni-shared

Capa MAS BAJA del monorepo `keni-social`: la **fuente UNICA importable** de las
definiciones canonicas que antes estaban espejadas (con guards) entre modulos.

Hasta ahora el catalogo de marca, los limites de plataforma, `io_atomico` y
`engagement_pct` estaban **unificados de valor** pero **no importados de una sola
fuente**: el catalogo canonico vivia en la consola, que `keni-metricas` NO puede
importar (direccion de dependencia), asi que `keni-metricas` y los artefactos de
skills lo ESPEJABAN con guards. Este paquete invierte esa relacion: la definicion
vive AQUI, y tanto `keni-metricas` como `keni-consola` dependen de `keni-shared` e
importan de el. Los guards verifican contra esta fuente unica.

```
              keni-shared            (sin dependencias internas)
             /          \
   keni-metricas      keni-consola   (ambos dependen de keni-shared)
```

## Que vive aqui

- **`keni_shared.marcas`** — catalogo canonico de marca (ids `slug-guion`,
  `id_metricas` `guion_bajo`, etiquetas humanas) y los helpers de la frontera con
  metricas. UNA marca = UN id.
- **`keni_shared.limites_plataforma`** — limites tecnicos duros de caracteres por
  plataforma (la fuente unica de los topes; el frontend la lee por API y la skill
  por su guard).
- **`keni_shared.cuentas`** — la cuenta principal de deportes y sus cuentas
  hermanas (Claro Sports + canal de TV + golf).
- **`keni_shared.io_atomico`** — `escribir_atomico`: escritura atomica de texto a
  fichero (tmp en el mismo dir + `os.replace`).
- **`keni_shared.metricas`** — `engagement_pct`: la formula unica de engagement.

Sin estado ni I/O (salvo `io_atomico`, que toca disco por definicion). Solo datos
y funciones puras. No depende de pydantic, httpx ni de nada del resto del repo.

## Instalacion (editable, dentro del monorepo)

```bash
pip install -e ./keni-shared
```

El resto de paquetes lo arrastran como dependencia, asi que normalmente basta con
`pip install -e ./keni-shared -e ./mcp-metricas -e ./consola`.
