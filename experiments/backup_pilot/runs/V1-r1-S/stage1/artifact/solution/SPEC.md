# Especificación V1

Referencia normativa: `/trial/CONTRACT.md`, preservado sin modificaciones.
Python 3.12, exclusivamente biblioteca estándar. Variante V1: primera versión
funcional, con todas las garantías base del contrato.

## Criterios de aceptación derivados antes de implementar

| ID | Requisito / criterio observable | Verificación prevista |
| --- | --- | --- |
| C01 | Cuatro comandos; éxito código 0 y exactamente un objeto JSON con el esquema contractual; lista ordenada | CLI y ejemplos |
| C02 | Copia exacta de archivos regulares (incluidos vacíos y bytes arbitrarios), nombres Unicode/espacios y todos los directorios vacíos | Comparación de árboles, hashes y bytes |
| C03 | Restauración autosuficiente sin fuente; creación no modifica la fuente | Borrar fuente después de comparar su inventario |
| C04 | ID estrictamente ASCII, 1–64 caracteres; IDs ausentes y existentes se rechazan según el comando | Casos de límite y duplicación |
| C05 | Rechazar enlaces simbólicos y objetos especiales en fuente, repositorio, snapshots, destino y componentes de sus rutas; no seguirlos | Enlaces internos/externos/rotos, FIFO y socket |
| C06 | Fuente y repositorio no pueden solaparse en ninguna dirección | Igualdad, ascendencia y descendencia |
| C07 | Destino existente no vacío conserva sus bytes; ID existente conserva su snapshot | Comparaciones antes/después de fallos |
| C08 | Publicación atómica; temporales no aparecen en list; SIGKILL permite repetir el ID y preserva snapshots anteriores | Matar create tras observar su temporal; verificar y repetir |
| C09 | Alteración/eliminación de datos o metadatos impide verify exitoso y restauración publicada | Mutaciones de cada archivo del snapshot; destino ausente y vacío |
| C10 | Errores tienen código no cero, nunca JSON de éxito; entradas malformadas se rechazan | CLI y manipulación de manifiestos |
| C11 | List en repo nuevo vacío da []; solamente snapshots completos | Repositorio vacío y temporales/incompletos |
| C12 | Entrega documentada, pruebas ejecutadas y comandos/resultados conservados | README, plan, tareas, implementación e informe |

## Decisiones de formato y comportamiento

Repositorio: `snapshots/ID/{data/,manifest.json,COMMIT}` y `.staging/` para
operaciones no publicadas. El manifiesto enumera cada ruta relativa y su tipo;
cada archivo incorpora tamaño y SHA-256. COMMIT contiene el SHA-256 de los bytes
del manifiesto. El verificador exige inventario exacto y metadatos estrictos.
Los hashes detectan corrupción accidental; no son una firma de autenticidad.

La publicación utiliza rename del árbol completo en el mismo filesystem.
Los temporales de procesos muertos se ignoran y no bloquean repetir el ID;
no se eliminan temporales ajenos. Restore construye un temporal hermano del
destino, comprueba los archivos copiados y lo publica al final. Se rechaza el
solapamiento destino/repositorio para proteger los datos del repositorio.

List valida los snapshots publicados antes de incluirlos; un snapshot publicado
corrupto provoca error. Directorios sin COMMIT se consideran incompletos y se
omiten. Un repositorio inexistente se trata como vacío solamente en list.
No se requiere preservar permisos, propietarios, tiempos ni identidad hardlink.
La fuente se supone estable conforme al contrato. El entorno objetivo es POSIX
(el contenedor del piloto), con nombres de archivo propios de ese entorno.

## Trazabilidad

Los tests se nombrarán con los criterios C01–C11. La documentación de ejecución
vinculará cada criterio a pruebas ejecutadas y registrará los comandos exactos.
