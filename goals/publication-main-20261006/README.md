# Publicación e integración de main

Se reúne la línea de resultados y metas con el toolkit tipado rc3.dev2 y sus experimentos prospectivos, preservando cada campaña histórica y el GOAL alimentario original. Se añaden el piloto de backups antes sin trackear, su producto, la entrega RangeAudit original, la web reconstruible y las instrucciones de Docker.

La suite específica pasó 186 pruebas y 46 subpruebas. El wheel recién construido e instalado fuera del árbol pasó el smoke CLI/MCP real: 24 herramientas, 15 operaciones compartidas, nueve fases sintéticas, recuperación SIGKILL y rechazo de firmas/entradas. Estos controles sintéticos no son una nueva campaña ni una generación nativa.

**La suite completa del host no está validada:** fue interrumpida tras 216.66s con 696 pasadas, 45 fallos, 43 errores y 13 subpruebas. Los logs conservan problemas de fuentes históricas y el digest revisado de pdftotext; no se afirma que ese pin explique todos los fallos. No se cambiaron pines ni resultados para hacerla pasar. La imagen release conserva el extractor fijado en su Dockerfile; clonar el repositorio no modifica el extractor del host.

El primer intento de ejecutar el smoke desde la instalación editable fue rechazado correctamente, porque exige un wheel instalado en site-packages. Se conserva ese rechazo y el posterior resultado de la instalación limpia.

Se omitieron perfiles/cuentas, sesiones, credenciales, caches, locks y productos npm de build. Los eventos y paquetes originales de experimentos conservan sus bytes; sus rutas registradas son históricas y no se sustituyen por el nuevo checkout.
