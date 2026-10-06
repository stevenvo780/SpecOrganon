# Especificación V2

Referencia normativa: `/trial/CONTRACT.md`, conservado sin cambios. Esta primera
versión se construye desde cero con Python 3.12 y biblioteca estándar, sin red.

## Criterios derivados antes de implementar

| Criterio | Comportamiento observable | Verificación prevista |
| --- | --- | --- |
| AC01 | Los cuatro comandos usan la interfaz contractual; éxito: código 0 y un único objeto JSON con las claves indicadas. Errores: código distinto de 0, sin éxito falso. | `test_cli_and_empty_repository`, `test_invalid_ids_and_missing_snapshots` |
| AC02 | Copiar bytes arbitrarios, nombres Unicode/espacios y todos los directorios, incluidos vacíos; fuente intacta. | `test_successive_versions`, `test_empty_source` |
| AC03 | V2: cada ID captura independientemente adiciones, modificaciones y eliminaciones; restaurar versiones antiguas sin acceso a la fuente. | `test_successive_versions` |
| AC04 | Validar exactamente `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; nunca sobrescribir un ID publicado. | `test_invalid_ids_and_missing_snapshots`, `test_existing_id_is_preserved` |
| AC05 | Fuente y repositorio no pueden coincidir ni contenerse; detectar antes de escribir. | `test_source_repository_overlap` |
| AC06 | Rechazar symlinks, incluso en componentes ancestrales, en fuente, repositorio, snapshots y destino; no seguirlos. | `test_symlinks_are_rejected`, `test_symlink_parent_and_dotdot` |
| AC07 | Rechazar FIFO, sockets y otros tipos especiales en árboles gestionados. | `test_special_files_are_rejected` |
| AC08 | Un destino no vacío se rechaza sin cambiar sus bytes. Un destino vacío o inexistente puede publicarse solo después de verificar. | `test_protected_destination`, `test_empty_existing_destination` |
| AC09 | Verificar inventario exacto, tamaños y SHA-256 de todos los datos y la integridad del manifiesto. Corrupción o eliminación impiden éxito de verify/restore. | `test_corruption_of_every_snapshot_file`, `test_extra_and_missing_entries` |
| AC10 | Publicar snapshots completos mediante un único rename; temporales nunca se listan. SIGKILL preserva snapshots anteriores y permite repetir el mismo ID. | `test_sigkill_and_retry`, `test_unpublished_staging_is_not_listed` |
| AC11 | `list` devuelve IDs ordenados de snapshots completos comprobables; repositorio vacío o inexistente devuelve `[]`. | `test_cli_and_empty_repository`, `test_successive_versions`, `test_unpublished_staging_is_not_listed` |
| AC12 | Un repositorio es autosuficiente; ninguna restauración lee la fuente original. | `test_successive_versions` |
| AC13 | Metadatos con rutas absolutas, escapes, duplicados o estructura inválida son rechazados antes de escribir un destino. | `test_invalid_manifests` |
| AC14 | Fallos de copia o publicación no dejan un destino publicado parcialmente ni anuncian éxito. | `test_copy_failure_is_not_published`, `test_restore_copy_failure_is_not_published` |

## Decisiones técnicas dentro del contrato

- Repositorio privado: `snapshots/ID/{manifest.json,manifest.sha256,data/}`;
  `.staging/create-UUID/` aloja operaciones no publicadas. `.lock` serializa los
  comandos del programa con `fcntl.flock` en el entorno POSIX del piloto.
- Cada snapshot contiene una copia completa. El manifiesto canónico enumera todos
  los directorios y archivos; su resumen queda en un registro de longitud fija.
  Detectar corrupción accidental no implica autenticar cambios coordinados de
  datos y sus hashes por un adversario.
- `list` comprueba los snapshots publicados y omite los corruptos/incompletos;
  un symlink o archivo especial en cualquier parte del repositorio causa error.
- Los directorios de repositorio vacíos son aceptables; otros nombres en su raíz
  se rechazan. Los temporales válidos abandonados se eliminan al siguiente create
  bajo el bloqueo; un ID reservado dentro de `snapshots/` nunca se sobrescribe.
- Restore primero verifica el snapshot y copia a un temporal hermano del destino;
  vuelve a comprobar hashes durante la copia y publica mediante rename. Rechaza
  solapamiento entre destino y repositorio para proteger sus datos.
- No se preservan permisos, propietarios, tiempos, ACL ni relaciones hardlink.
  La fuente permanece estable durante create, según el contrato. No se promete
  resistencia frente a un tercero que sustituya directorios concurrentemente.
- Se sincronizan archivos y directorios antes de publicar. La garantía exigida
  de interrupción es SIGKILL; no se exige tolerancia universal a fallo de hardware.

## Límites y errores

Los errores se escriben como un objeto JSON en stderr, con código 1 (errores de
operación) o 2 (uso inválido). stdout queda reservado para el resultado exitoso.
Cada árbol se valida sin seguir enlaces. Un destino no vacío se comprueba antes
de cualquier cambio. Las rutas del manifiesto deben ser relativas, únicas y
tener sus directorios padres explícitos.
