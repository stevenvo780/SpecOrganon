# Primera ejecución y ajuste de las pruebas

Comando (directorio de trabajo `/trial`):

```text
python3 -m unittest discover -s solution -p test_backup.py -v
```

Resultado: código 1; 21 tests ejecutados en 7.460 s, 20 correctos y 1 error.
El test `test_C05_special_nodes_source_repo_snapshot_dest` intentó crear un socket
AF_UNIX; el contenedor rechazó `socket.bind` con
`PermissionError: [Errno 1] Operation not permitted`. Su limpieza intentó después
eliminar un socket que no llegó a existir y produjo `FileNotFoundError`.
Las pruebas de copia exacta, corrupción de cada archivo, SIGKILL y recuperación
pasaron en esta ejecución. No se cambió backup.py por este resultado.

Ajuste: separar el socket real en un test que registra omisión si el entorno
prohíbe bind; usar unlink(missing_ok=True). Mantener FIFO reales y añadir una
prueba de clasificación de todos los tipos especiales usando stat_result.
Añadir pruebas de errores de copia/publicación para cerrar la verificación de
limpieza y protección del destino. No se cambia la especificación ni el contrato.
