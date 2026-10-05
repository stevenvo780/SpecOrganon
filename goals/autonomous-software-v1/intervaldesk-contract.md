# Contrato público de IntervalDesk v1

Este es un nuevo caso de transferencia técnica del controlador corregido.
LogLens permanece inconcluso; esta entrega no es una réplica de aquel intento,
una comparación reservada N/S/T ni una demostración de eficacia de campo.
El expediente requiere nueve fases sustantivas, revisiones reales separadas,
criterios anteriores a las pruebas, trazas y una entrega utilizable.

## Entrega y comportamiento

Entregar `cover.py`, pruebas del contrato y `README.md`, con Python 3.12 y sólo
su biblioteca estándar. `python cover.py INPUT` lee un archivo UTF-8 JSON con
exactamente la clave `intervals`: una lista de hasta 1000 pares `[start,end]`.
Los extremos son enteros exactos (booleanos excluidos) y cumplen
`0 <= start < end <= 1440`. Son intervalos semiabiertos de un día abstracto;
no corresponden a una población real de reuniones ni a beneficios sociales.

Devolver un objeto JSON con exactamente `merged`, `covered_minutes` e
`input_count`. La unión `merged` está ordenada por inicio; une solapamientos
y adyacencias. Por ejemplo `[0,5]` y `[5,10]` se unen en `[0,10]`.
`covered_minutes` suma la longitud de los intervalos de la unión, e
`input_count` cuenta los pares de entrada, incluidos duplicados. El orden
original no cambia la unión. Una lista vacía devuelve `[]`, 0 y 0.

Ejemplo público:

```json
{"intervals":[[5,10],[0,7],[10,12],[20,25]]}
```

Resultado:

```json
{"merged":[[0,12],[20,25]],"covered_minutes":17,"input_count":4}
```

Dos copias de `[1,3]` producen `merged=[[1,3]]`, duración 2 e input_count 2.
La igualdad se evalúa sobre el JSON decodificado, no sobre orden de claves,
espacios o indentación. El éxito devuelve exit 0; stdout sólo contiene el JSON.

Una entrada inválida, archivo inexistente/ilegible, BOM, UTF-8 inválido,
clave duplicada/desconocida o archivo mayor que 65536 bytes falla con exit 2,
stderr no vacío y stdout vacío. No aceptar flotantes, NaN/Infinity, extremos
invertidos ni pares de longitud distinta de 2. No modificar el archivo de
entrada ni realizar solicitudes de red. `--help` explica el uso y devuelve
exit 0. Aceptar espacios JSON ordinarios. El README explica formato, ejemplos,
ejecución desde carpeta limpia, errores y límites de interpretación.

## Investigación y pruebas

Investigar la representación de intervalos y los límites del parser; comparar
alternativas sustantivas antes de elegir una. No inventar tiempos, usuarios,
experimentos o aprobaciones. La elección de arquitectura es delegación técnica,
no una elección personal del dueño. El protocolo y los criterios deben preceder
la medición. Los argumentos de las fases se redactan por el autor, no se infieren
de plantillas ni de la existencia de campos.

Las pruebas pertinentes cubren éxito, lista vacía, solapamientos, adyacencias,
orden, duplicados, errores de esquema/tipo, límites y conservación de entrada.
Autorías sólo proponen argv/command, sin `passed`, recibos ni mediciones inventadas.
El controlador ejecuta después de registrar criterios y conserva salida real.
No convertir la unión abstracta de intervalos en mejor productividad o impacto.

El ejecutor limpio usa `/opt/specorganon/venv/bin/python`; la entrega está en
`/input/delivery`, de sólo lectura. Usar `/output` o TMPDIR para archivos de
prueba. No dispone de red, perfiles de modelos ni el workspace del autor.
Las pruebas deben invocar la CLI, no sólo probar funciones importadas.

## Fuentes documentales verificadas antes de autorías

Fecha de consulta: 2026-10-05 UTC. Son fuentes sobre APIs, no mediciones del
programa futuro ni argumentos preescritos para sus fases.

- [Python 3.12: json](https://docs.python.org/3.12/library/json.html), apartados
  Basic Usage, Encoders and Decoders y Standard Compliance. El decodificador
  permite interceptar constantes y pares de claves; el comportamiento por
  defecto acepta ciertos valores no estándar y conserva el último valor de
  nombres repetidos. El contrato exige restricciones adicionales.
- [Python 3.12: argparse](https://docs.python.org/3.12/library/argparse.html),
  apartados help y Exiting methods. Documenta ayuda y control de errores de CLI;
  no valida el contenido JSON ni garantiza el contrato del programa.

## Límites fijados

Una sola ejecución nueva, hasta 40 llamadas de rol; dos respuestas de autor y
dos juicios incluyendo conformidad del mandato por fase. Cada rol: 180 s,
prompt máximo 128000 bytes y 2 MiB por stream. Global: 6000 s. Un error, timeout
o respuesta inválida queda registrado; no cambiar cuenta/modelo para eludirlo.
Una reparación de artefactos tras rechazo debe cambiar materialmente el trabajo
y respetar el presupuesto. No reintentar un trabajo incierto sin recibo.

Máximo dos ejecuciones por test, 120 s cada una; una segunda requiere un cambio
de código ejecutable. Imagen limpia fija, sin red/perfiles, 1 GiB, 2 CPU y
128 procesos. No atribuir costes ausentes: uso informado se registra y dinero
desconocido queda desconocido. La publicación exige las nueve fases vigentes,
trazas completas, pruebas medidas, README revisado y un ejemplo limpio real.
