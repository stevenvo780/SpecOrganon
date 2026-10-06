# Resultados de pruebas V3

Python 3.12.15. Todos los datos de prueba se crearon en directorios privados de /trial.

Primera ejecución: `python3.12 -m unittest discover -s solution -p test_backup.py -v`. Código 1: 19 tests, 3 errores del propio arnés al intentar interpretar como JSON el diagnóstico de argparse para `--id -bad`. El programa rechazó ese ID y no emitió éxito. Se corrigió el arnés para pasar `--id=-bad`, y se añadieron pruebas de varios bloques e interrupción del manifiesto. Los comandos y salidas individuales de ambas ejecuciones se conservan en TEST_COMMANDS.jsonl.

Ejecución tras esos cambios:

```text
$ python3.12 -m unittest discover -s solution -p test_backup.py -v
test_arbitrary_names_and_nested_missing_parent (test_backup.BackupTests.test_arbitrary_names_and_nested_missing_parent) ... ok
test_corruption_does_not_publish_missing_destination (test_backup.BackupTests.test_corruption_does_not_publish_missing_destination) ... ok
test_corruption_every_regular_file (test_backup.BackupTests.test_corruption_every_regular_file) ... ok
test_empty_source_and_existing_empty_destination (test_backup.BackupTests.test_empty_source_and_existing_empty_destination) ... ok
test_existing_id_never_overwritten (test_backup.BackupTests.test_existing_id_never_overwritten) ... ok
test_extra_object_or_missing_manifest_is_incomplete (test_backup.BackupTests.test_extra_object_or_missing_manifest_is_incomplete) ... ok
test_failure_during_restore_leaves_destination_and_cleans_stage (test_backup.BackupTests.test_failure_during_restore_leaves_destination_and_cleans_stage) ... ok
test_invalid_ids (test_backup.BackupTests.test_invalid_ids) ... ok
test_links_in_roots_ancestors_repo_snapshot_and_destination (test_backup.BackupTests.test_links_in_roots_ancestors_repo_snapshot_and_destination) ... ok
test_manifest_validation_and_traversal (test_backup.BackupTests.test_manifest_validation_and_traversal) ... ok
test_multiple_stream_chunks (test_backup.BackupTests.test_multiple_stream_chunks) ... ok
test_new_empty_repositories_and_unknown_ids (test_backup.BackupTests.test_new_empty_repositories_and_unknown_ids) ... ok
test_overlap_rejected_before_mutation (test_backup.BackupTests.test_overlap_rejected_before_mutation) ... ok
test_protected_destination (test_backup.BackupTests.test_protected_destination) ... ok
test_round_trip_and_source_independence (test_backup.BackupTests.test_round_trip_and_source_independence) ... ok
test_sigkill_after_publication_leaves_complete_snapshot (test_backup.BackupTests.test_sigkill_after_publication_leaves_complete_snapshot) ... ok
test_sigkill_before_publication_retries_and_preserves_previous_snapshots (test_backup.BackupTests.test_sigkill_before_publication_retries_and_preserves_previous_snapshots) ... ok
test_source_links_and_special_files (test_backup.BackupTests.test_source_links_and_special_files) ... ok
test_special_files_in_repo_and_destination (test_backup.BackupTests.test_special_files_in_repo_and_destination) ... ok
test_versions_and_sorted_listing (test_backup.BackupTests.test_versions_and_sorted_listing) ... ok

----------------------------------------------------------------------
Ran 20 tests in 4.789s

OK
Código de salida: 0
```
