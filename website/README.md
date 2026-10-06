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

## Dev4 y cierre terminal de dev2

`#avance-dev4` publica 296 controles del host y 296 del wheel instalado, CLI/MCP24 y nueve diagnósticos de sintaxis (seis fallos, tres válidos); no son generaciones de software. `#cohorte-nativa` muestra el cierre dev2: diez intentos, tres entregas y siete fallos, sin reemplazos. Se incumple el 90%; no hay superioridad demostrada. La cohorte dev4 02 está registrada prospectivamente con 45 fuentes, y está en ejecución; todavía no se publican resultados finales. Los 54 archivos descargables anteriores y sus manifiestos conservan sus bytes. Siete descargas nuevas se añaden en `avance-dev4/`, con hashes separados.

## Dev5 y observación de cohorte dev4

`#avance-dev5` publica 328 controles del host y 328 del wheel instalado, CLI/MCP24 y tres controles Docker reales con pérdida de respuesta inyectada. No reproduce el timeout natural ni acredita fiabilidad nativa. La observación separada de dev4, fechada 03:43:23 UTC, conserva seis cierres, dos entregas y cuatro fallos; la cohorte sigue en sus fuentes congeladas. Dev5 no tiene cohorte nativa; libre/SDD sólidos son un diseño pendiente. Se conservan las 61 descargas anteriores y se añaden 12 en `avance-dev5/` con hashes separados.

## Dev6 parcial, sin wheel liberado

`#avance-dev6` publica formatos neutrales y helpers de evidencia común, 389 pruebas acotadas aprobadas y tres omitidas; las revisiones son estáticas y la aceptación se limita a helpers. El wheel dev6 sólo se probó localmente, con 34 módulos iguales y CLI exit0: no se descarga ni se presenta como versión completa. No hay smoke MCP nuevo, generación dev6 o comparación ejecutada. El último wheel público es dev5. Ocho descargas nuevas conservan protocolo pendiente, recibo, revisiones, logs y snapshot dev4 fechado; las 73 anteriores permanecen intactas.

## Cierre terminal de la cohorte dev4

`#cohorte-dev4-cierre` publica el informe original del 6 de octubre a las 04:23:28 UTC: diez intentos cerrados, cinco entregas y cinco fallos sin reemplazos. Cinco entregas pasaron 543/543 comprobaciones públicas en conjunto; el denominador de fiabilidad sigue siendo diez. Resultado50%, Wilson descriptivo23,66–76,34%, criterio9/10 incumplido. El archivo conserva fuentes45 y recibos seleccionados, con paths históricos; no permite reanudar runs desde main. Se añaden cinco descargas terminales a las ocho de dev6, manteniendo las73 anteriores intactas. Total86.

## Controladores dev6 por etapas, todavía parciales

`#controles-dev6` conserva 627 pruebas seleccionadas aprobadas,16 omitidas y13 controles Docker mecánicos reales ejecutados aparte, con fixtures y un Gemini CLI simulado, cero modelos. El wheel local verificó36 módulos,CLIexit0 yMCP host24; no se libera ni acredita imagen dev6 instalada. Revisión final limitada R17/R14–R16 sin runtime del revisor. Cero nativos/reservados; F/common_complete desconocidos; pendiente competencia N/S, integración T/común, evaluación independiente, registro y congelación. Ocho descargas nuevas tienen manifiesto propio y fuente69f64d; las86 anteriores permanecen intactas. Los ZIP fuente parcial/evidencia se extraen en la misma raíz para `verify_archive.py --check-source`; no constituyen una release completa o una campaña ejecutable.

## Dev7 instalado, ingeniería parcial

`#avance-dev7` documenta controlador N libre durable v2 y driver instalado schema2: 186 pruebas seleccionadas, primer lote Docker19pass1fixturefail conservado, tres pruebas nuevas afectadas corregidas3pass (otros17 no repetidos), 40 módulos iguales en wheel/imágenes locales, CLI0.160 yMCP24. Revisión Gemini estática limitada; cero nativos/reservados ysin competencia ni superioridad. No release/registry nuevo; último wheel público dev5. Se conservan94 descargas exactas. Los cortes dev6 anteriores se presentan como históricos.

## Piloto dev7: corte parcial report-01

`#piloto-dev7` muestra2 cierres failed de6 y4 sin resultado en ese corte, no estado live. Ambos RangeAudit N/S pasaron115/115 pero sinD/Gfinal/paquetecomún; fallo compartido exactrequestbudget. Diagnóstico offline131968>110000bytes sin retry/dispatch:history89938 antesouterescaping,rolepackets30947,captures58708.504originales sellados e índiceSHA,511entradas de evidencia. No aumentarcuotas/reemplazar intentos; versión/registro futuros prospectivos. Último wheel público dev5,94descargas anteriores exactas,no ranking/competencia/superioridad. Corte dev7ingeniería previo separado.

## Piloto dev7 terminal, informe final separado

`#piloto-dev7` presenta cierre original08:56:26UTC:6/6failed exactrequestbudget,0/6gatecomplete,648/648checks públicos descriptivos (115/104/105 cada brazo),sinD/Gfinal/common_complete/F externo ni competencia/superioridad/ranking. Report01de2/6queda histórico inmutable. Nuevos1080originales22311295bytes+504anteriores,manifiesto1087.19rolesnativos13author6review+3ownmeasures,22controllercontainers exitedretained/nocleanup;wholeattemptsum1830.455sec,no ratioscomparativos.94descargas históricas intactas/no nueva release. Futurocodec/versionseparados,nopublicadosenestehito.
