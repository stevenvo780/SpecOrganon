# D-103 · Cobertura instalada completa de interfaces

**Criterio 1 cumplido en alcance técnico:** wheel D-102, Linux,
Python 3.11.15 y 3.12.3, contrato inventariado. Revisión independiente de
archivos y efectos por `/root/prototype_checkpoint_supervisor`.
GOAL y la matriz de aceptación permanecen intactos. **Aceptación: 1/5**;
los otros cuatro criterios siguen No demostrados. No es un porcentaje de
avance global ni un resultado alimentario.

## Resultados y procedencia

El [plan previo](plan.json) parte de 16/22 operaciones positivas por ambos
transportes en Python 3.11 y 6/22 en 3.12 sobre el wheel actual D-102.
El [inventario final](coverage.json) cubre **22/22 en ambos intérpretes**:
15 del smoke real, seis transportes firmados y el auditor de lotes D-102.
Cada fila enlaza invocación CLI/MCP, paridad y comprobación de efectos.
El wheel SHA `e155d010a17a1235f071da6b0d89c1773b5dc92295a85251873f1880c448390b`
coincide con los 24 módulos instalados y con el árbol fuente actual.

| Control | Python 3.11.15 | Python 3.12.3 |
| --- | --- | --- |
| Operaciones positivas CLI/MCP | 22/22 | 22/22 |
| Tests de seis transportes firmados | 3 passed; 9 etapas sin skips | 3 passed; 9 etapas sin skips |
| Workflow `signed_observed` | 9 fases; 51 eventos; 29 ítems | 9 fases; 51 eventos; 29 ítems |
| Ejecución local y repetición en sandbox | Landlock ABI 9 en repetición | Landlock ABI 9 en repetición |
| Dos agentes nativos actuales | 4 ítems únicos; 5 eventos | 4 ítems únicos; 5 eventos |
| Solapamiento inducido de actividad | 184 922 046 ns | 173 400 743 ns |
| Mayor solapamiento de llamadas CLI | 64 283 469 ns | 57 624 802 ns |
| Pares CLI/MCP del caso nativo | 4, sin escrituras | 4, sin escrituras |

[Controles críticos](critical_checks.json): rechazos de entradas/firmas,
fallos observables, SIGKILL real, prefijo duradero, recuperación MCP,
replay sin duplicados, invalidación por bytes y revocación de claves.
Instalaciones limpias y smoke 3.11 están en D-102; smoke 3.12, seis
transportes y ambos workflows firmados se ejecutaron en D-103.
No se reconstruyó el wheel. Se añadieron cinco dependencias de pytest
offline: `uv pip check` confirma 34 paquetes compatibles por entorno.
La suite global D-102 de 2560 pruebas es evidencia anterior; D-103 ejecuta
verificaciones integradas y Ruff/compilación de sus tres scripts.

Los threads existentes `/root/subscription_method_broker_099` y
`/root/source_gate_review` ejecutaron sus propias llamadas reales del CLI.
Cada uno tiene dos IDs disjuntos, versión esperada 0 y dependencias fijadas.
El supervisor verificó PIDs vivos y `wchan=wait_for_partner` antes de abrir
ambos FIFOs y liberar `x`. `ready.json` por sí solo no prueba esa espera.
Los recibos y el ledger prueban consumo y escrituras posteriores;
el solapamiento proviene de la barrera y no demuestra ventaja de modelos.

La primera prueba nativa cubría sólo 3.11. La auditoría literal de la matriz
exigió completar esa prueba crítica en ambos entornos. Se congeló un
[plan complementario](native_environment_completion_plan.json) antes de
ejecutar un caso nuevo en 3.12 con los mismos threads y helper.
El criterio y su umbral permanecen iguales. Workflow completo y
coordinación son coberturas separables según GOAL y la matriz §7.
La aprobación humana competente y la comparación confirmatoria de agentes
siguen pendientes para sus ámbitos; no se añaden como requisitos de C1.

## Archivos y fallos conservados

[Ocho archivos tar e inventarios](archives.json) conservan 196 archivos
regulares: casos, registros públicos de claves, entradas, bundles y
artefactos. No se almacenan claves privadas. Enlaces simbólicos de pytest
son sólo metadatos y no se siguen. Los FIFOs no se archivan como archivos
ordinarios. Las trazas gzip conservan streams CLI y objetos originales
del SDK; no son frames MCP. El descubrimiento SDK completo se conserva
en ambos casos nativos. Los 15 controles del smoke se sustentan en su
resumen y código fijado, sin stream separado por cada llamada.

- Ambos primeros capturadores terminaron con código 2 después de que los
  tres tests reales pasaran. Pytest abreviaba `nodeid` al usar raíz externa;
  el guard esperaba un archivo. La enmienda valida ruta canónica y función
  exactas, conservando los IDs originales. Nuevos destinos finales pasan;
  los originales siguen fallidos y no se reescribieron.
- La revisión previa del escritor exigió entorno mínimo, pines del wheel
  y del caso firmado y FIFO auténtico. Se corrigió antes de lanzar agentes.
  El resultado `put` se coteja como ítem normalizado, no como evento.
- El agregador inicial falló con `KeyError: isError`: el SDK D-102 usaba
  snake_case. Se conservan [código inicial](archive_initial_executed.py)
  y [código final](archive_final_executed.py), con reanudación sólo de bytes
  idénticos. El error se atribuye a salida observada de la tool; no se
  reconstruye un stderr original que no se guardó en archivo.
- La sonda firmada original borraba sus directorios temporales. Sus dos
  resultados quedan como resúmenes originales separados. La opción nueva
  `--workspace-root` permitió conservar dos verificaciones adicionales con
  ledgers/bundles inspeccionables. Son controles mecánicos de desarrollo,
  sin repetición de antiguos ensayos de modelos.

[Congelación inicial](source_freeze.json), [enmienda](source_freeze_amendment.json)
y [cotejo posterior](source_post_execution.json) distinguen versiones.
La segunda prueba nativa conserva su [agregador](archive_native312_executed.py)
y la primera snapshot del inventario crítico. Los recibos prospectivos
mantienen su `0/5` anterior; el veredicto consolidado posterior está en
[la revisión](review.json) y [el recibo final](receipt.json).

## Repetición

Desde una instalación nueva offline del wheel D-102:

```bash
VENVPYTHON -I scripts/clean_smoke.py /workspace/SpecOrganon
VENVPYTHON -I scripts/probe_installed_signed_transports.py /workspace/SpecOrganon NUEVO_DIRECTORIO
VENVPYTHON -I scripts/probe_signed_full_workflow.py /workspace/SpecOrganon --test-gate-policy signed_observed --workspace-root NUEVO_WORKSPACE
```

El capturador requiere pytest instalado y destino externo nuevo. La prueba
nativa requiere caso signed con `p_native`, dos FIFOs y dos agentes:
el [helper](../../../scripts/probe_installed_native_writer.py) exige wheel,
ID de caso y hash del proyecto. Comandos originales y controles del
supervisor están en `native/` y `native/312/`. Agregadores y verificadores
archivados fijan rutas originales; recomputar requiere esos archivos o
adaptar las rutas de lectura. El primer agregador coteja 97 pines antes de
actualizar documentación; ese paso requiere sus versiones D-102 en una
snapshot aislada. El recibo final distingue los 94 archivos conservados
de los tres documentos activos actualizados. El toolkit de producción
no cambió en D-103.

## Límites y siguiente frente

Firmas y registros de confianza son sintéticos, locales al mismo UID.
No autentican consentimiento, competencia humana, custodia externa,
proveedor/modelo efectivo o ejecución histórica externa. La observación
del test de transporte usa un bundle prefabricado; la sonda firmada
separada ejecuta y repite realmente el comando con entrada fijada.
Los nueve avances pertenecen a casos signed de contenido sintético;
los casos nativos mantienen cero aprobaciones, reviews o fases aceptadas.

No hay Q, nueva corrida confirmatoria N/SDD/T, autorización normativa,
intervención de campo ni corrida de las 24. C2–C5 siguen No demostrados.
El siguiente trabajo continúa con auditoría de linaje de requisitos e
indicadores y análisis de salidas exploratorias conservadas, preparando
evaluación independiente sin inventar evidencia.
