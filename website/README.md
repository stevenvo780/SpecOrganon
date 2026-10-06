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

Para renovar el corte documental, desde la carpeta padre:

```sh
python3 build_public.py
```

El generador lee el checkout vecino y escribe exclusivamente los dos archivos
de esta presentación: `public/project.json` y `src/project-data.json`. No ejecuta
el código ni las pruebas de SpecOrganon. La disponibilidad de enlaces individuales
a GitHub procede de `/tmp/specorganon-public-tree.json`, un inventario leído de la
rama pública; si no existe, no genera enlaces a archivos sin verificar.

La evaluación editorial del responsable se conserva en `../public_assessment.json`.
El generador la aplica a los cinco criterios, identifica su autor y conserva la
auditoría documental anterior en `documentary_acceptance`. Para actualizar solo
esta evaluación sobre el corte existente: `python3 build_public.py --assessment-only`
desde la carpeta padre.

La construcción en Vercel usa el JSON ya preparado y no necesita acceso al checkout
vecino, Python ni al servidor del observatorio.

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

Al publicar, la rama pública de https://github.com/stevenvo780/SpecOrganon contenía
únicamente `GOAL.md`. La guía operativa requiere el checkout completo de desarrollo.
La página muestra esta diferencia y ofrece únicamente enlaces documentales
comprobados en el árbol público.

Esta edición pública es un corte documental. El observatorio Python de la carpeta
padre conserva su actualización local por SSE; Vercel no observa el filesystem
del contenedor. Renovar la edición pública requiere generar el JSON y desplegar.

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

Para volver a exportar la evidencia desde el checkout hermano de SpecOrganon:

```sh
cd ..
python3 publish_backup_results.py
python3 build_public.py --assessment-only
cd web
npm run build
```

El exportador necesita Python y el paquete `markdown`, ya disponible en el host.
El build de Vercel solo necesita las fuentes React y los archivos públicos ya
exportados; no accede al checkout del experimento. Las exportaciones públicas
omiten streams brutos, sesiones y rutas privadas. Solo cambia metadata de los
dos archivos tar originales: las fuentes ejecutables se conservan byte a byte.
`descargas-manifest.json` contiene los hashes de las distribuciones públicas.

Sitio: https://specorganon.stevenvallejo.com/#resultados
Informe sin JavaScript: /resultados/backup/RESULTADOS.html
