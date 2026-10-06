# Implementación final V1 con --max-bytes

## Correspondencia con la especificación

| Decisión | Implementación en backup.py | Criterios |
| --- | --- | --- |
| Validación de rutas y tipos sin seguir symlinks | checked_path, directory, inventory, regular_reader | C05, C06, C11 |
| Inventario exacto, copia y SHA-256 por bloques de 1 MiB | inventory, digest_file, tree_path | C02, C03, C08 |
| ID y manifiesto estricto, sello y árbol exacto | check_id, unique_object, validate_manifest, verified_snapshot | C04, C08 |
| Presupuesto opcional decimal no negativo | byte_limit y parser | C12 |
| Suma de todos los st_size regulares | repository_bytes y check_budget | C13, C14 |
| Escritor exclusivo sin archivo de bloqueo | create_lock mediante fcntl.flock del directorio | C09, C13, C15 |
| Recuperación de preparación abandonada | discard_abandoned_staging bajo bloqueo | C09, C15 |
| Preparación privada, limpieza en finally y rename atómico | create, stage_snapshot | C01–C04, C09, C13, C14 |
| Verificación completa antes de afirmar validez | verify y verified_snapshot | C01, C08 |
| Preparación hermana y rehash antes de publicar destino | empty_destination, restore | C01, C03, C07, C08 |
| IDs ordenados, solo snapshots íntegros | list_snapshots | C04, C10 |
| JSON único tras terminar; error en stderr | main | C01, C11 |

## Transacción de create

Se inspecciona la fuente sin cambiarla, se rechaza solapamiento y se valida
el repo. Si el uso existente supera el límite, se falla antes de preparar
nuevos archivos. Se inicializan únicamente los directorios del formato y se
adquiere un bloqueo exclusivo sobre el directorio del repo. Bajo bloqueo se
revalida el repo, la ausencia del ID y el presupuesto, y se elimina staging
abandonado. Ningún proceso create de este programa puede borrar la preparación
activa de otro porque la preparación ocurre dentro del mismo bloqueo.

stage_snapshot copia los datos a un directorio privado, crea ambos archivos
regulares de metadata y sincroniza archivos y directorios. check_budget suma
también los datos y metadatos que aún están en staging. El rename cambia solo
rutas, por lo que la suma comprobada es la suma final. Si la medición rechaza,
finally borra el directorio privado; los snapshots publicados quedan intactos.

Los snapshots incompletos/corruptos que un actor externo haya puesto en
snapshots no se borran: sus archivos cuentan en el límite, su ID sigue ocupado
y list no los presenta como válidos. Toda metadata necesaria para reconstruir
el árbol está en los archivos regulares del manifiesto/sello. El bloqueo es
estado transitorio del núcleo y desaparece al cerrar el descriptor o morir
el proceso; no se usa para almacenar información persistente.

## Recuperación y errores

SIGKILL antes de rename puede dejar staging, pero jamás publica ese árbol.
SIGKILL después de rename deja un snapshot ya completo. No se sobrescriben
IDs publicados. La limpieza de staging se hace únicamente por create; verify,
restore y list no mutan el repo. Rechazos por capacidad dejan una suma de
archivos igual o menor a la inicial. Una fuente vacía puede fallar con N=0
por sus metadatos, dejando solo directorios vacíos.

restore compara hashes antes y durante la copia. La publicación del destino
ocurre después de verificar todos los archivos; ante corrupción no se devuelve
éxito ni se publica un árbol como correcto. La limpieza de preparaciones propias
también se ejecuta al recibir KeyboardInterrupt; ante SIGKILL el sistema no
ejecuta finally y la recuperación de create se realiza en el siguiente intento.

## Límites y ajustes de las pruebas

Se verifica Python 3.12/Linux, cuya biblioteca estándar incluye fcntl. No se
garantiza compatibilidad con Windows. El límite es lógico por archivo, no uso
físico ni máximo transitorio. Los hardlinks se copian como archivos independientes
y su st_size se contabiliza por entrada regular. La fuente debe ser estable;
los actores externos que sustituyen rutas concurrentemente quedan fuera del
alcance declarado. No hay garantía de recuperación ante fallo de energía.

La evidencia anterior contenía un error al intentar crear un socket Unix
prohibido por el contenedor. Se separó esa prueba de los rechazos de enlaces y
FIFO: únicamente la prueba real de socket queda omitida ante PermissionError.
No se simula ni se afirma su cobertura real. Las evidencias anteriores se
conservan como históricas; las actuales llevan sufijo max-bytes.
