# Reporte del Piloto

## Limitaciones
- n=6 por brazo
- un modelo configurado, no snapshot verificado
- cegamiento imperfecto
- cuotas compartidas
- muestras del mismo dominio
- revisión local declarada
- sin eficacia de campo demostrada

## Selección de Producto
Producto seleccionado: **V1-r1-N**
## Resumen por Brazo y Etapa
| Brazo | Etapa | Score Medio | Score Mediana | Rango | Críticos | Inconclusos |
|---|---|---|---|---|---|---|
| N | 1 | 0.783 | 1.000 | [0.350, 1.000] | 0 | 0 |
| N | 2 | 0.545 | 0.318 | [0.318, 1.000] | 0 | 0 |
| S | 1 | 0.783 | 1.000 | [0.350, 1.000] | 0 | 0 |
| S | 2 | 0.773 | 1.000 | [0.318, 1.000] | 0 | 0 |
| T | 1 | 1.000 | 1.000 | [1.000, 1.000] | 0 | 0 |
| T | 2 | 0.985 | 1.000 | [0.909, 1.000] | 0 | 0 |

## Diferencias Pareadas
| Comparación | Etapa | Score Delta Medio | Mediana | Rango |
|---|---|---|---|---|
| T-N | 1 | 0.217 | 0.000 | [0.000, 0.650] |
| T-S | 1 | 0.217 | 0.000 | [0.000, 0.650] |
| T-N | 2 | 0.439 | 0.682 | [-0.091, 0.682] |
| T-S | 2 | 0.212 | 0.000 | [-0.091, 0.682] |

## Adaptación (Cambio en Checks Comunes y Nuevos)
| Run | Delta Comunes (Puntos) | Delta Comunes (Score) | max_bytes_high | max_bytes_low |
|---|---|---|---|---|
| V2-r2-N | 0 | 0.000 | False | False |
| V3-r1-N | 0 | 0.000 | True | True |
| V2-r1-N | -13 | -0.650 | False | False |
| V1-r2-N | -13 | -0.650 | False | False |
| V3-r2-N | 0 | 0.000 | False | False |
| V1-r1-N | 0 | 0.000 | True | True |
| V2-r2-S | 0 | 0.000 | True | True |
| V3-r1-S | 0 | 0.000 | False | False |
| V2-r1-S | 0 | 0.000 | True | True |
| V1-r2-S | 0 | 0.000 | True | True |
| V3-r2-S | 0 | 0.000 | False | False |
| V1-r1-S | 0 | 0.000 | True | True |
| V2-r2-T | 0 | 0.000 | True | True |
| V3-r1-T | 0 | 0.000 | True | True |
| V2-r1-T | 0 | 0.000 | True | True |
| V1-r2-T | 0 | 0.000 | True | True |
| V3-r2-T | 0 | 0.000 | True | True |
| V1-r1-T | 0 | 0.000 | False | False |

## Resultados Detallados (18x2)
| ID | Arm | Var | Rep | Etapa | Score | Checks | Críticos | Inconclusos | Tiempo (A+M) | Hash Candidato | Coste |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V2-r2-T | T | V2 | 2 | 1 | 1.000 | 20/20 | 0 | No | 600.2s | 72e5ec6f | null |
| V2-r2-T | T | V2 | 2 | 2 | 1.000 | 22/22 | 0 | No | 600.2s | 0907d4dc | null |
| V2-r2-S | S | V2 | 2 | 1 | 1.000 | 20/20 | 0 | No | 600.1s | 93918a41 | null |
| V2-r2-S | S | V2 | 2 | 2 | 1.000 | 22/22 | 0 | No | 600.1s | 1cc0e1ab | null |
| V2-r2-N | N | V2 | 2 | 1 | 0.350 | 7/20 | 0 | No | 600.1s | bf62256f | null |
| V2-r2-N | N | V2 | 2 | 2 | 0.318 | 7/22 | 0 | No | 360.1s | b6e14e3e | null |
| V3-r1-N | N | V3 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.1s | 9de7764d | null |
| V3-r1-N | N | V3 | 1 | 2 | 1.000 | 22/22 | 0 | No | 377.6s | 380cc556 | null |
| V3-r1-S | S | V3 | 1 | 1 | 0.350 | 7/20 | 0 | No | 600.1s | bcf36270 | null |
| V3-r1-S | S | V3 | 1 | 2 | 0.318 | 7/22 | 0 | No | 600.3s | f40ae0a2 | null |
| V3-r1-T | T | V3 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.3s | 62a5147a | null |
| V3-r1-T | T | V3 | 1 | 2 | 1.000 | 22/22 | 0 | No | 600.2s | afb338a6 | null |
| V2-r1-N | N | V2 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.1s | 53d4d105 | null |
| V2-r1-N | N | V2 | 1 | 2 | 0.318 | 7/22 | 0 | No | 600.1s | a93d0b0a | null |
| V2-r1-T | T | V2 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.2s | 581d0525 | null |
| V2-r1-T | T | V2 | 1 | 2 | 1.000 | 22/22 | 0 | No | 600.2s | f4fe8737 | null |
| V2-r1-S | S | V2 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.1s | 6fc6567c | null |
| V2-r1-S | S | V2 | 1 | 2 | 1.000 | 22/22 | 0 | No | 599.0s | 55ff3d5a | null |
| V1-r2-S | S | V1 | 2 | 1 | 1.000 | 20/20 | 0 | No | 600.2s | eedde192 | null |
| V1-r2-S | S | V1 | 2 | 2 | 1.000 | 22/22 | 0 | No | 600.2s | 39a16655 | null |
| V1-r2-T | T | V1 | 2 | 1 | 1.000 | 20/20 | 0 | No | 600.2s | cfa97c66 | null |
| V1-r2-T | T | V1 | 2 | 2 | 1.000 | 22/22 | 0 | No | 600.2s | 75f4b530 | null |
| V1-r2-N | N | V1 | 2 | 1 | 1.000 | 20/20 | 0 | No | 600.1s | 9e8277d5 | null |
| V1-r2-N | N | V1 | 2 | 2 | 0.318 | 7/22 | 0 | No | 600.1s | 10a6df96 | null |
| V3-r2-T | T | V3 | 2 | 1 | 1.000 | 20/20 | 0 | No | 600.2s | 01297094 | null |
| V3-r2-T | T | V3 | 2 | 2 | 1.000 | 22/22 | 0 | No | 600.6s | 4cfddb9d | null |
| V3-r2-N | N | V3 | 2 | 1 | 0.350 | 7/20 | 0 | No | 600.1s | b1fdb2d3 | null |
| V3-r2-N | N | V3 | 2 | 2 | 0.318 | 7/22 | 0 | No | 600.1s | 1c391ad5 | null |
| V3-r2-S | S | V3 | 2 | 1 | 0.350 | 7/20 | 0 | No | 600.1s | 3209b96d | null |
| V3-r2-S | S | V3 | 2 | 2 | 0.318 | 7/22 | 0 | No | 600.1s | b1ae2a4e | null |
| V1-r1-S | S | V1 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.3s | cd2d8e4c | null |
| V1-r1-S | S | V1 | 1 | 2 | 1.000 | 22/22 | 0 | No | 600.1s | 885473ea | null |
| V1-r1-N | N | V1 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.1s | 68fbb75b | null |
| V1-r1-N | N | V1 | 1 | 2 | 1.000 | 22/22 | 0 | No | 331.8s | eaac5ef5 | null |
| V1-r1-T | T | V1 | 1 | 1 | 1.000 | 20/20 | 0 | No | 600.2s | b10e934b | null |
| V1-r1-T | T | V1 | 1 | 2 | 0.909 | 20/22 | 0 | No | 600.3s | b10e934b | null |

## Recursos por etapa y rol
Cada celda resume seis corridas; cache es parte de input y no se suma otra vez. Desconocido no significa cero.

| Brazo | Etapa | Rol | Tiempo mediano (s) | Input mediano | Output mediano | Cache mediana | Usos input ausentes |
|---|---|---|---|---|---|---|---|
| N | 1 | author | 600.1 | desconocido | desconocido | desconocido | 6/6 |
| N | 1 | review | 89.6 | 49359.5 | 2184.0 | 33216.0 | 0/6 |
| N | 2 | author | 488.9 | 281861.0 | 10349.0 | 228864.0 | 3/6 |
| N | 2 | review | 85.2 | 51001.0 | 1598.0 | 28672.0 | 1/6 |
| S | 1 | author | 600.1 | desconocido | desconocido | desconocido | 6/6 |
| S | 1 | review | 86.7 | 47594.0 | 1855.5 | 34624.0 | 0/6 |
| S | 2 | author | 600.1 | 325493.0 | 17931.0 | 254976.0 | 5/6 |
| S | 2 | review | 96.7 | 65864.0 | 2005.0 | 46336.0 | 1/6 |
| T | 1 | author | 480.1 | desconocido | desconocido | desconocido | 6/6 |
| T | 1 | method | 120.1 | desconocido | desconocido | desconocido | 6/6 |
| T | 1 | review | 92.0 | 53295.5 | 2230.5 | 40704.0 | 0/6 |
| T | 2 | author | 480.1 | desconocido | desconocido | desconocido | 6/6 |
| T | 2 | method | 120.1 | desconocido | desconocido | desconocido | 6/6 |
| T | 2 | review | 86.8 | 45690.0 | 2166.0 | 24448.0 | 0/6 |

## Fallos críticos conservados

La selección es una sugerencia técnica sujeta a comprobar el producto en un runtime limpio y publicar su procedencia. Las diferencias de piloto no prueban eficacia general ni de campo. Costes monetarios desconocidos.