# D-101 · Receta documental alimentaria auditada y reanudable

**Resultado técnico de desarrollo; aceptación GOAL: 0/5.** La receta publica
37 ítems pendientes después de repetir D-100: 17 cantidades y siete filas
archivadas de encuesta. Conserva los dos desacuerdos entre prosa y tablas.
No interpreta esos agregados como un lote actual, efecto causal o resultado
de campo. No hubo llamadas experimentales nuevas a modelos, aprobación
humana o ensayo de campo. Agentes Codex participaron en código y revisión.

## Implementación y decisiones

- [Controlador](../../../scripts/run_audited_bread_recipe.py): `prepare`,
  `status` y `run --transport cli|mcp`. La preparación fija copias de los dos
  PDF, claims, Tabla 1, contrato y resultado del auditor; no crea un ledger.
- La publicación se reconstruye desde el cotejo nuevo y exige igualdad de
  texto, cantidad, unidad, base, procedencia, locador y digest del pasaje.
  Modificar coherentemente sidecars y hashes no reemplaza esa extracción.
  Contrato y código deben coincidir con el corte revisado. Las siete filas
  se archivan en un ítem de evidencia; no se anuncian siete ítems nuevos.
- El manifiesto CLI se transmite mediante un memfd sellado. MCP recibe el
  objeto ya validado y raíz/registro público explícitos. Un éxito de
  transporte exige un ledger real y completo de 37 eventos, cursor 37 y
  resultado `waiting / independent_review_required` conciliado con el caso.
- Un checkpoint admite sólo un prefijo ordenado de esos `item_put`, versión
  1 y actor previsto. También coteja identidad del proyecto y política
  `signed`. Revisiones, versiones nuevas, eventos ajenos o política
  `fixture` requieren una revisión explícita de la receta; no se reparan.
- La receta contiene actores, límites, dos formulaciones rivales, concepto
  de valor plural, norma pendiente, pregunta, hipótesis, protocolo documental,
  evidencia, indicador, inferencia y incertidumbres. Es un comienzo de
  formulación/investigación: no ejecuta las nueve fases ni aprueba una norma.

## Prueba real instalada

[Sonda](../../../scripts/probe_audited_bread_recipe.py) con el wheel final
D-100 ya instalado offline, en dos entornos independientes. La instalación
original y SHA del wheel están en el
[dossier D-100](../bread_source_audit_2026-09-30/receipt.json). El wheel no se
reconstruyó porque este corte sólo añade scripts y pruebas. La sonda exige
importación desde `site-packages`, y los pines locales del controlador,
auditor y módulo instalado coinciden. Esto no autentica una autoridad externa
del wheel o del publicador.

| Comprobación | Python 3.11.15 | Python 3.12.3 |
|---|---:|---:|
| SIGKILL real tras escrituras durables | 16 | 16 |
| MCP nuevo: aplicados / omitidos | 21 / 16 | 21 / 16 |
| CLI posterior: aplicados / omitidos | 0 / 37 | 0 / 37 |
| Dirección inversa MCP → CLI | 37 → 0 / 37 | 37 → 0 / 37 |
| Controles: seis archivos × mutar/quitar/symlink | 18 | 18 |
| Pares iguales de status/gate/next, sin escritura | 39 | 39 |
| Herramientas MCP descubiertas | 21 | 21 |

Se conservan prefijo 16, checkpoint 37, control firmado 39 y cambio de
supuesto 40 eventos. Los 18 controles invalidan evidencia y dependientes,
instantánea, revisión y avance; conservan una rama independiente. La
restauración exacta de bytes recupera la instantánea anterior. Cambiar el
supuesto a versión 2 invalida dependientes y bloquea replay viejo sin
sobrescribirlo. No hay publicación duplicada ni escritura por consultas.

La firma del control usa una clave **sintética sólo en RAM**, con identidad
pública separada. Revisión, avance de `frame` y actualización del supuesto
son acciones mecánicas externas a la receta de 37 puts: no son aceptación
humana o científica. El propio controlador rechaza ese ledger divergente.
`n_harm` sigue sin aprobación. Esos controles no se cuentan como nueve fases,
tratamiento N/SDD/T completo o corrida de las 24 exigidas.

Los [recibos 3.11](installed/311/receipt.json) y
[3.12](installed/312/receipt.json) contienen detalles y pines. Las respuestas
originales CLI/MCP están en `transports.jsonl.gz`, compresión sin pérdida de
8.347.135 bytes por entorno; el SHA del contenido descomprimido corresponde
a `trace_sha256`. Los nombres de `/tmp` en los registros identifican el
runtime observado; una copia archivada de registro público no vuelve a
autorizar automáticamente otra ruta de caso.

## Correcciones, negativos y conservación

La revisión reprodujo y cerró tres falsos verdes: CLI que imprime éxito sin
ledger, caso `fixture` presentado como `signed` y revisión ajena al prefijo.
Las regresiones incluyen cantidades/bases falsas antes de inicialización,
sidecars coherentemente falsificados, symlinks, manifest alterado al lanzar
y estado divergente. **50 pruebas focales pasan en cada Python**, Ruff y
compilación; [registros](validation.json). No se repitió la suite global.

El primer prototipo publicó 37 ítems por CLI y MCP falló por raíz implícita.
Se conserva su controlador, caso y [nota de operador](preliminary_root_failure/operator_note.json);
sus streams originales no quedaron guardados y no se reconstruyen. Otro
intento de tests bajo Python global falló por `mcp` ausente al importar;
los imports de transporte son ahora locales a esa rama. Los cambios son
desarrollo del controlador; no reparan ni reemplazan ensayos de modelos.

[Conservación](preservation.json): 272 protegidos, 147 outputs D-099, 12
marcadores, 22 módulos fijados por su plan, 16 archivos de su dossier
congelado y 21 pines de código/evidencias D-100 sin discrepancias. Sus tres
documentos activos de estado/validación/decisiones se actualizan en D-101;
los 24 pines coincidían antes de esa actualización y los anteriores quedan
en el commit padre. Procesos nuevos leen
D-099 S/T/N como `completed` y D-097 como `failed`; no hubo otro turno,
replay o sustitución de ese negativo. [Revisión independiente](review.json).

## Límites de integridad y aceptación

La auditoría semántica vive en **esta frontera de receta**. Un `put` directo
del motor puede eludirla: bytes PDF válidos por sí solos no comprueban el
valor de una afirmación. La interfaz genérica no incorpora una comprobación
universal de semántica documental.

La operación **no es una transacción atómica de archivos y ledger**. Un
cambio concurrente posterior al audit puede dejar un prefijo o los 37 puts
escritos. Una regresión muta el PDF justo antes de `run`: los valores
publicados permanecen auditados (736), pero archivo y dependientes quedan
inválidos, `frame.ready` falso y el control final rechaza con `RecipeError`.
No se promete impedir todo `item_put` después de una modificación concurrente.
Se conserva ese checkpoint rechazado para inspección; no se fuerza avance.
Restaurar los bytes exactos puede reactivar una revisión mecánica anterior.

Contrato revisado por Codex, host/bibliotecas sin atestación, fuentes
históricas/agregadas y autoinformes, sin seguimiento real de lotes,
comparador causal, autoridad normativa, panel de calidad o custodia externa.
`Q:null`; cinco criterios **No demostrados**. D-099 muestra uso posible de
Luna en tareas acotadas, sin demostrar equivalencia de calidad.

## Reproducción y siguiente frente

Desde un entorno con el paquete D-100 final y dependencias instalado:

```bash
python scripts/run_audited_bread_recipe.py prepare /tmp/bread-audited-new
python scripts/run_audited_bread_recipe.py run /tmp/bread-audited-new --transport cli
python scripts/run_audited_bread_recipe.py run /tmp/bread-audited-new --transport mcp
python scripts/run_audited_bread_recipe.py status /tmp/bread-audited-new
python scripts/probe_audited_bread_recipe.py /tmp/bread-probe-new
```

Las rutas deben ser nuevas y el binario `pdftotext` debe coincidir con el
contrato D-100. Cambiar código requiere nueva preparación. Linux/memfd/proc
son dependencias declaradas. Ningún comando de la receta aprueba normas.

Siguiente frente: ampliar el caso en formulación/crítica/especificación e
ingeniería con obligaciones derivadas de los valores y causas explícitas de
bloqueo, conservando las fuentes auditadas. La aceptación final sigue
exigiendo workflow completo instalado, cadena real de valor y comparación
causal de campo, comparación preregistrada entre métodos/modelos/esfuerzos y
transferencia completa al segundo dominio. GOAL permanece íntegro.
