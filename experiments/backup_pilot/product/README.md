# Backup verificable

Producto local del piloto de SpecOrganon. Requiere **Python 3.12 en Linux**
y usa exclusivamente la biblioteca estándar. No necesita instalación con pip.
La implementación es la entrega `V1-r1-N`, etapa dos, sin modificaciones.

Desde esta carpeta:

```bash
python3 backup.py create --source /ruta/fuente --repo /ruta/repo --id copia_1 --max-bytes 100000000
python3 backup.py verify --repo /ruta/repo --id copia_1
python3 backup.py list --repo /ruta/repo
python3 backup.py restore --repo /ruta/repo --id copia_1 --dest /ruta/restaurada
```

La fuente contiene archivos regulares y directorios. El destino debe ser nuevo
o estar vacío. Los IDs admitidos son `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`; una copia
existente no se sobrescribe. Cada comando exitoso devuelve un único objeto JSON:

```json
{"id": "copia_1"}
{"id": "copia_1", "valid": true}
{"snapshots": ["copia_1"]}
```

Crear y restaurar devuelven el primer formato, verificar el segundo y listar el
tercero. Los errores retornan un código distinto de cero y diagnóstico por stderr.
`list` requiere un directorio de repositorio existente; uno vacío devuelve una
lista vacía. Solo lista copias completas e íntegras.

`--max-bytes` es opcional. Limita la suma de bytes de todos los archivos regulares
del repositorio, incluidos snapshots anteriores, datos y metadata. Si no cabe,
la creación se rechaza y conserva las copias anteriores. No hay compresión ni
deduplicación. Los directorios vacíos también requieren metadata y pueden no
caber con límite cero.

La restauración funciona aunque se haya eliminado la fuente original. Conserva
los bytes, nombres Unicode/espacios y directorios vacíos; no conserva UID, ACL,
tiempos ni identidad de hardlinks. Rechaza symlinks, archivos especiales y el
solapamiento de fuente/repositorio. La fuente debe permanecer estable durante
la operación. Las operaciones de esta herramienta se serializan con `fcntl`.

Una interrupción de `create` puede dejar datos sin publicar en `.staging`. Para
recuperar, repite el mismo comando: la herramienta limpia el temporal y libera
el bloqueo al terminar el proceso. Si ya se publicó la copia, el ID existe y
la repetición se rechaza. No borres manualmente snapshots válidos para reintentar.
`verify` comprueba manifiesto, tamaños y SHA-256; una corrupción impide verificar
o restaurar como correcto. Los hashes detectan corrupción accidental, pero no
autentican una copia frente a quien reescriba datos, manifiesto y sello juntos.

## Verificación conservada

La misma fuente pasó **22/22 comprobaciones en cada una de V1, V2 y V3**, en
Python 3.12.15 sin paquetes del entorno, con candidato UID1000, sin red y código
en solo lectura. Incluye restauración exacta, versiones, corrupción, SIGKILL,
repetición del create incompleto, destinos protegidos, IDs, symlinks, FIFO y cuota.
Las 32 pruebas propias y el ejemplo también terminaron con código 0 en un
contenedor aislado. El ejemplo verifica bytes y directorios después de eliminar
la fuente, y conserva el repositorio al rechazar una cuota insuficiente.

Esta comprobación posterior a la selección usa las familias y semillas ya
evaluadas; no constituye un nuevo holdout independiente ni cambia los resultados
del piloto. Los recibos completos están en `../analysis/product-verification/`.

Para comprobar la evidencia y repetir solo tareas sin recibo previo, desde la
raíz de SpecOrganon:

```bash
python experiments/backup_pilot/verify_product.py
```

Los recibos terminados se validan y reutilizan. Un marcador de tarea iniciada
sin recibo final exige inspección y disposición explícita; no provoca una
repetición favorable automática. Una ejecución nueva necesita un directorio
nuevo de observaciones y debe conservar las anteriores.

`test_backup.py` y `examples.py` son pruebas y ejemplos conservados de la entrega;
se ejecutaron con los comandos exactos y montajes que registra el verificador.
El producto operativo solo necesita `backup.py`.

## Procedencia y límites

SHA-256 de `backup.py`:

```text
eaac5ef5622e77d5584474318baba62f906ff1030d6cdcad8fcf7275886e6e0a
```

`provenance.json` conserva la ruta de origen y hashes. `README.candidate.md` es
la documentación original del autor; este README añade las instrucciones de
entrega y los resultados verificados por el controlador.

Se seleccionó una implementación de trabajo libre que pasó las pruebas y tuvo
menor tiempo de autoría entre los candidatos elegibles. El producto no pretende
demostrar que SpecOrganon produjo el mejor programa individual ni validar el
GOAL.md original de campo y generalización. En el proyecto, `../RESULTADOS.md`
contiene el veredicto y `../README.md` las instrucciones de reproducción. El
paquete independiente del producto puede usarse sin ese proyecto; el informe
también se distribuye en el paquete de fuentes del experimento, bajo
`experiments/backup_pilot/RESULTADOS.md`.
