# SpecOrganon · presentación pública

**Producción:** https://specorganon.stevenvallejo.com

**Fuentes del proyecto:** https://github.com/stevenvo780/SpecOrganon/tree/main

La presentación se incluye en `website/` dentro del repositorio compartido. El toolkit está en la raíz; esta carpeta usa npm para construir la web.

Presentación en React 19, TypeScript y Vite 8, con Motion y Lucide. Tipografías
Geist, Instrument Serif y JetBrains Mono servidas desde el propio sitio.

## Experiencia

- Grafo conceptual con inspección mediante ratón, teclado y toque.
- Explorador de nueve fases con contratos extraídos de `workflow.py` mediante AST.
- Demostración de dependencias obsoletas ante una hipótesis nueva.
- Arquitectura del toolkit e inventario de las 24 herramientas MCP descubiertas.
- Guía configurable para políticas `local`, `signed` y `fixture`, copia de comandos
  y descarga de un documento Markdown con los nueve contratos de fase.
- Cinco casos documentales, criterios de aceptación, cronología y búsqueda de
  120 títulos de decisiones.
- Navegación móvil, foco visible, respeto a movimiento reducido y vista de impresión.
- Mapa independiente con temas y exportación; sus controles están en inglés.

## Desarrollo

Desde esta carpeta:

```sh
npm ci
npm run dev -- --host 0.0.0.0
npm run build
npm run preview -- --host 0.0.0.0
```

## Datos y corte documental

El clon incluye `src/project-data.json` y `public/project.json`, además de los
resultados y manifiestos de descargas. `npm run build` utiliza esos archivos
versionados y permite reproducir la presentación sin acceder al entorno original.

La revisión `824d9f3`, su fecha y la valoración editorial conservan el corte
histórico. Los avances posteriores se registran en los datos de campañas y del
candidato rc3.dev2. Para actualizar contenido, modifica los datos correspondientes,
conserva sus fuentes y verifica los enlaces a `main` antes de publicar.

Los comandos de generación del entorno original no forman parte de este clon.
La construcción en Vercel usa el JSON preparado y las fuentes de esta carpeta.

## Publicar

```sh
vercel link --yes --project specorganon-presentacion --scope stevenvo780s-projects
vercel --prod --yes --scope stevenvo780s-projects
```

La presentación publica enlaces a la rama main de SpecOrganon y conserva los
resultados históricos junto a los avances nuevos. La autorización de Vercel está en la sesión del operador;
este proyecto no contiene credenciales ni variables secretas.

## Alcance del corte publicado

El JSON identifica la revisión local `824d9f3` y la fecha UTC de preparación.
El MVP está documentado como listo para uso técnico local: dos proyectos con nueve
fases aceptadas, replay sin eventos nuevos, control de invalidación 9 → 2,
24 herramientas MCP descubiertas y 263 pruebas de regresión documentadas.
Estos resultados pertenecen al dossier revisado; la presentación no reejecuta
la suite del proyecto. La evaluación actual del responsable declara completos
C1–C5 y el sistema maduro para usarse; el siguiente paso es disponer de más casos
de aplicación. El estado de los experimentos del corte documental se conserva.

En el corte inicial, la rama pública contenía únicamente `GOAL.md`. Desde la
publicación de avances del 6 de octubre de 2026, `main` contiene el toolkit, Docker,
los ejemplos, las campañas y esta web. La guía operativa clona esa rama y sus
enlaces documentales apuntan a archivos comprobados en el árbol público.

Esta edición pública es un corte documental. El observatorio Python de la carpeta
padre conserva su actualización local por SSE; Vercel no observa el filesystem
del contenedor. Renovar la edición pública requiere actualizar los datos versionados y desplegar.

## Verificación

- TypeScript y compilación Vite correctos, también en la construcción de Vercel.
- Escritorio de 1440 y 1920 px; móviles de 390 y 320 px sin desbordamiento horizontal.
- Contratos de las nueve fases, cuatro frentes y navegación de fases por teclado.
- Cambio y restauración de hipótesis, inspección de dependencias y 24 herramientas.
- Las tres políticas, habilitación explícita de fixtures y título citado de forma segura.
- Copia al portapapeles, descarga con nueve fases, cinco casos y búsqueda de decisiones.
- Cierre del registro con Escape, navegación móvil y preferencia de movimiento reducido.
- Acceso anónimo HTTP 200 a página, datos, imagen social y mapa independiente.

Mapa Archify entregado tras 9/9 comprobaciones, sin errores ni avisos de composición.
Control visual automático en 1440×900, 1600×1000, 1920×1080 y 2048×1320; inspección
visual de los temas claro y oscuro. El archivo publicado coincide byte por byte
con el artefacto validado:

```text
public/diagrams/recorrido.html
SHA-256: 377fc14f5e30ea3f18936f9dcc21b8c5d4282e2a782128549c370a20bbfe8d61
```

Los recibos y capturas de Archify permanecen en `../public-site/diagrams/`.
Los diagnósticos de navegador de esta publicación están en
`/tmp/spec-presentation-checks/`; son archivos temporales de verificación.

## Piloto autónomo de backups publicado el 4 de octubre de 2026

La sección `#resultados` presenta las 18 ejecuciones N/S/T y 36 entregas, las
puntuaciones funcionales, los hallazgos adversos de documentación y adherencia,
el producto seleccionado y la evidencia descargable. El piloto no acredita la
tesis general ni completa el objetivo original de campo.

Los resultados de este piloto ya están exportados en `public/resultados/backup/`.
El clon compartido permite construirlos con `npm ci` y `npm run build`, sin un
checkout hermano ni dependencias Python. Los exportadores del entorno original
pertenecen al historial de preparación y no son requisitos de esta distribución.

Las exportaciones públicas omiten streams brutos, sesiones y rutas privadas.
Solo cambia metadata de los dos archivos tar originales: las fuentes ejecutables
se conservan byte a byte. `descargas-manifest.json` contiene los hashes de las
distribuciones públicas.

Sitio: https://specorganon.stevenvallejo.com/#resultados
Informe sin JavaScript: /resultados/backup/RESULTADOS.html

## Cohorte nativa en curso

La sección `#cohorte-nativa` publica una foto fechada de diez intentos fijos, sus contratos y su primer fallo, sin mezclar la entrega RangeAudit anterior con el denominador. Las fuentes del registro y del driver están en main. La foto no es un monitor en vivo ni acredita fiabilidad o superioridad; los resultados posteriores se publican como nuevos hitos. Las 32 descargas históricas permanecen intactas.

## Candidato dev3 y snapshot 02

La sección `#avance-dev3` publica las verificaciones de ingeniería 193/193, wheel y límites del candidato schema12; no afirma eficacia nativa. `#cohorte-nativa` muestra el snapshot 02 dev2 de cinco cierres, cuatro fallos y una entrega. Los enlaces del snapshot 01 y las 38 descargas anteriores permanecen intactos. Las fuentes del frontend y sus JSON permiten reconstruir esta foto; no es un monitor en vivo.
