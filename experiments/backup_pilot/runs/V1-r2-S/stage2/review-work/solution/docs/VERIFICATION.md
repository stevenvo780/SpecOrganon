# Verificación final y trazabilidad

Los criterios C01–C11 se conservaron y C12–C15 se documentaron antes de adaptar
la implementación al contrato actualizado. No se usaron resultados de revisión
externa ni datos de evaluación reservada.

## Comandos y resultados reales

Ejecutado desde `/trial` con Python 3.12.15:

```sh
python3 solution/tests/run_checks.py
```

| Comando ejecutado por el runner | Resultado | Evidencia |
| --- | --- | --- |
| python3 -m unittest discover -s solution/tests -p 'test_*.py' -v | Código 0; 28 pruebas, 27 aprobadas, 1 omitida; 8.961 s | evidence/tests-max-bytes.txt |
| python3 solution/tests/example.py | Código 0; EXAMPLE PASS | evidence/example-max-bytes.txt |
| python3 -m py_compile solution/backup.py solution/tests/test_backup.py solution/tests/example.py solution/tests/run_checks.py | Código 0 | evidence/compile-max-bytes.txt |
| Comparación SHA-256 del contrato al inicio/final | Sin cambios | evidence/contract-max-bytes.txt |

El archivo de cada ejecución conserva el comando exacto (incluida la ruta del
intérprete), fecha UTC, versión, stdout, stderr y código. Las pruebas usan
directorios privados temporales en `/trial/solution/tests`, que se limpian.
Los resultados históricos sin sufijo max-bytes pertenecen a la versión previa.

## Matriz de aceptación

Los nombres de pruebas siguientes son los de métodos en tests/test_backup.py.

| Criterio | Pruebas ejecutadas | Evidencia observable |
| --- | --- | --- |
| C01 | C01_C02_C03_roundtrip_autonomous_and_source_unchanged; ejemplo; run_cli común | JSON exacto, una línea, códigos y stderr |
| C02 | C02_deep_tree_large_bytes_and_posix_names; C02_empty_source_and_existing_empty_destination; roundtrip | Bytes, nombres, árbol profundo y directorios vacíos exactos |
| C03 | roundtrip; C13_high_limit_counts_all_metadata_and_roundtrip; ejemplo | Fuente intacta y retirada antes de restore |
| C04 | C04_sorted_ids_exact_versions_and_no_overwrite; C04_invalid_and_boundary_ids; C04_missing_snapshot | Versiones exactas, IDs límite, orden, ausencia y no sobrescritura |
| C05 | C05_source_links_and_specials; C05_symlink_ancestors_and_before_dotdot; C05_repo_root_link_and_fifo; C05_repo_staging_and_snapshot_unsafe_entries; C05_dest_link_fifo_and_internal_link | Rechazo de symlinks y FIFO en rutas gestionadas; socket omitido por entorno |
| C06 | C06_source_repo_overlap | Igualdad e inclusiones rechazadas, fuente intacta |
| C07 | C07_nonempty_destination_unchanged; C07_destination_repo_overlap; destino vacío | Bytes protegidos intactos, directorio vacío aceptado |
| C08 | C08_each_regular_snapshot_file_modified_or_removed; C08_extra_and_missing_tree_entries; C08_manifest_schema_and_path_validation | Cada archivo regular, incluidos metadata y archivo vacío, alterado/eliminado: verify y restore rechazan sin publicación |
| C09 | C09_SIGKILL_preserves_previous_and_retry_same_id | Proceso muerto con SIGKILL en copia; snapshot previo íntegro; reintento y restore exacto |
| C10 | C10_empty_absent_repo_and_incomplete_snapshots; matriz de corrupción | Repo vacío/ausente, staging e incompletos no se listan |
| C11 | C11_errors_and_wrong_root_types; run_cli; compilación | Biblioteca estándar, Python 3.12, errores sin stdout de éxito |
| C12 | C12_invalid_limits_leave_repo_absent; suite anterior sin límite | Decimal no negativo, ceros iniciales, argumentos inválidos rechazados antes de crear repo |
| C13 | C13_high_limit_counts_all_metadata_and_roundtrip; C13_metadata_cannot_be_excluded_for_empty_source; C13_C14_previous_snapshots_count_and_never_change; C13_C14_C15_staging_and_incomplete_files_count; C13_serialized_creates_cannot_exceed_global_budget | Oráculo independiente rglob/lstat cuenta todo, incluida metadata, archivos ocultos y entradas previas; concurrencia no excede presupuesto |
| C14 | C13_C14_exact_capacity_and_one_byte_short; C13_C14_previous_snapshots_count_and_never_change; staging; ejemplo | Rechazo repetido, N inferior al uso previo, un byte insuficiente, ninguna preparación nueva residual, snapshots/fuente intactos |
| C15 | C09_SIGKILL_preserves_previous_and_retry_same_id; staging | Reintento con capacidad final exacta, staging vacío y bytes iguales al presupuesto |

Las capacidades exactas se obtienen midiendo una creación real en un repositorio
independiente, sin reproducir el algoritmo de serialización del producto. Se
compara la firma del árbol mediante tamaños y hashes SHA-256 calculados desde
las pruebas, además de las verificaciones internas del programa.

## Restricción de entorno

C05_source_socket se omite porque AF_UNIX bind devuelve PermissionError
`[Errno 1] Operation not permitted`. La prueba permanece para entornos que lo
permitan. El producto rechaza todo tipo diferente de directorio/archivo regular;
ese rechazo se ejercitó realmente con symlinks y FIFO, pero el caso de socket
no pudo verificarse aquí. No se cuenta la omisión como prueba aprobada.

## Preservación del contrato

SHA-256 inicial y final de CONTRACT.md:
`8adcc50d4a0b8411195837403c0f8cbc5327e1e3e8da3ac943ec4d708a0019c1`.
