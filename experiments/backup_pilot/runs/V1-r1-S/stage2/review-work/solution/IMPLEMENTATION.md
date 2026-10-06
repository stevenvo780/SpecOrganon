# Implementación V1 con límite global

La revisión de SPEC.md, PLAN.md y TASKS.md se realizó antes de editar backup.py.
Se mantuvo el formato previo, compatible con repositorios de la interfaz original.
No se añadieron dependencias ni archivos de metadata al repositorio.

## Create y presupuesto

1. Validar argumentos, ID, componentes de rutas y ausencia de solapamiento.
   Inventariar la fuente sin seguir symlinks ni admitir nodos especiales.
2. Crear el directorio del repo si falta. Tomar flock exclusivo sobre su
   descriptor; volver a validar el repo bajo el bloqueo, comprobar el ID y
   preparar los directorios del formato. No recorrer el repo antes del bloqueo,
   para evitar competir con otro escritor que limpia o publica temporales.
3. Limpiar solamente `.staging/`, que contiene trabajo privado abandonado. Esta
   limpieza sigue a la comprobación de tipos de todo el repo: no se elimina ni
   sigue un enlace que un tercero haya dejado allí.
4. Si hay límite, `repository_bytes` recorre **todo** el repo y suma st_size de
   cada archivo regular. Rechazar inmediatamente si lo existente supera N.
5. Copiar al staging con SHA-256 en bloques de 1 MiB. Comprobar estabilidad de
   cada archivo y el inventario de la fuente. Escribir manifest.json y COMMIT,
   con flush/fsync. Ambos contienen toda la metadata persistente del snapshot.
6. Si hay límite, volver a sumar todo el repo, incluido el staging completo.
   Si supera N, rechazar y eliminar el temporal en finally. Como la publicación
   es un rename, la suma comprobada coincide con la suma tras el éxito.
7. Sincronizar directorios de datos de abajo hacia arriba; publicar con rename
   y sincronizar snapshots. Limpiar el temporal si sigue existiendo, sincronizar
   staging y cerrar el descriptor para liberar el bloqueo.

N se interpreta mediante un patrón decimal ASCII y un entero Python. El valor
es opcional; ningún límite se aplica a la interfaz original. Los hardlinks se
cuentan por ruta, sin deduplicar inodos. No se almacenan cuotas ni hashes en
xattrs, nombres de directorios o nodos especiales. Los nombres del formato sirven
para localizar archivos; el ID y todas las rutas de datos constan en el
manifiesto regular. El bloqueo de kernel es temporal y no requiere lockfile.

El espacio transitorio puede superar N; el contrato limita la suma **tras un
create exitoso**. Rechazos controlados no dejan crecimiento regular permanente.
Un SIGKILL puede dejar staging, pero no una publicación parcial; el siguiente
create elimina los restos bajo el bloqueo. Ningún snapshot previo se elimina.
Los fallos de IO se propagan sin una respuesta de éxito. El filesystem debe
permitir las operaciones de limpieza y rename; no se intenta reparar bytes
corruptos ni recuperar un filesystem roto.

## Garantías conservadas

`safe_path` comprueba los componentes incluso antes de normalizar `..`.
`inventory` clasifica lstat sin seguir enlaces y abre directorios con O_NOFOLLOW.
`open_regular` utiliza O_NOFOLLOW y O_NONBLOCK, y verifica fstat para rechazar
tipos especiales. `file_data` copia y calcula tamaño/hash de la misma lectura.

`manifest_entries` exige inventario exacto, checksum del manifiesto, JSON
canónico, claves únicas, esquema estricto, ID concordante y rutas relativas
seguras con padres completos. `verified_entries` comprueba los bytes de cada
archivo. Se detectan datos alterados, truncados, eliminados, extras y directorios
vacíos desaparecidos. La eliminación de COMMIT impide verificar/restaurar.

Restore valida el destino antes de escribir y crea un temporal hermano. Verifica
el snapshot completo antes de copiar, verifica cada copia, comprueba otra vez
que el destino está vacío y publica con os.replace. Un error anterior a la
publicación elimina el temporal; el destino protegido conserva sus bytes.

List valida los snapshots con COMMIT; omite staging y snapshots incompletos.
Verify/restore rechazan IDs inexistentes. Se mantienen respuestas contractuales
y mensajes de error JSON en stderr. Las comprobaciones base se ejecutaron de
nuevo después del cambio, incluida restauración sin acceso a la fuente.

## Archivos de pruebas

`test_backup.py` conserva los casos base y añade casos C13–C16. El contador
independiente de prueba utiliza os.walk y lstat, sin llamar al contador de
producción. Los presupuestos exactos se obtienen midiendo un repo de referencia
creado mediante CLI, evitando repetir la construcción del manifiesto en el test.
Las pruebas negativas comparan contenido antes/después y sumas completas.
`examples.py` conserva comandos, respuestas y fixtures reproducibles.
`run_checks.py` captura comandos, código de salida, duración, stdout y stderr.
