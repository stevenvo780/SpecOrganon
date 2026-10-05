# Protocolo prospectivo de software v1 — no prerregistrado

Estado: diseño ejecutable en preparación. Cero soluciones/celdas generadas.
Antes de generar deben completarse la auditoría del admission gate de campaña,
los checks finales de contexto/rúbrica y el manifiesto de congelación.
No se autoriza generación mediante la mera existencia de este documento.

## Pregunta, población y unidades

Comparar los paquetes N/libre, S/guía SDD concreta y T/SpecOrganon al entregar
RoutePlan y TreeMap. Los contratos son los archivos públicos de esta carpeta;
la guía S y la rúbrica se congelarán con ellos. No medir eficacia de campo o
superioridad general. Cada celda usa datos propios sin compartir borradores,
sesiones generadas ni resultados entre métodos.

Población fija: dos tareas × dos familias originales autorizadas (Codex6.1Sol
con esfuerzo explícito low; Gemini3.1ProHigh) × dos repeticiones × tres métodos
=24 celdas. Cuatro ablaciones A en repetición1, por tarea/familia. Total28.
Los clientes nativos crean llamadas/sesiones nuevas; no se controla su seed.
Las repeticiones son réplicas operativas, sin afirmar independencia estadística
ni potencia suficiente para generalizar. No reemplazar tareas, familias o cuentas.

## Orden propuesto antes de observar resultados

Ejecutar secuencialmente estos ocho bloques, de izquierda a derecha. A se coloca
al final de los bloques de repetición1. No elegir el próximo bloque por puntuación.

| Bloque | Tarea | Autor | Repetición | Métodos en orden |
|---|---|---|---|---|
| 1 | RoutePlan | Codex | 1 | N, S, T, A |
| 2 | TreeMap | Gemini | 1 | S, T, N, A |
| 3 | RoutePlan | Gemini | 2 | T, N, S |
| 4 | TreeMap | Codex | 2 | N, T, S |
| 5 | TreeMap | Codex | 1 | T, S, N, A |
| 6 | RoutePlan | Gemini | 1 | S, N, T, A |
| 7 | TreeMap | Gemini | 2 | N, S, T |
| 8 | RoutePlan | Codex | 2 | T, N, S |

Hay ocho posiciones por método principal; ocho no se divide por tres, por lo
que el balance de posiciones es aproximado. El orden y cada ID deben existir
en el manifiesto antes de admitir la primera llamada.

## Ejecución y feedback

N decide su proceso y puede conservar notas voluntarias. S produce SPEC, luego
DESIGN/TASKS antes del código. T utiliza el controlador schema6 y nueve fases
con revisiones y vínculos vigentes. A produce siete borradores de fase antes
del build y un borrador de validate tras medir; no inventa aprobaciones ni usa
el motor para aceptar fases. Es una ablación del conjunto de controles
intermedios, incluida su representación en el motor; no sólo de una bandera.

Todas las rutas sellan programa/README, añaden tests sin reemplazar esos bytes,
ejecutan tests públicos en un contenedor sin credenciales/red y conservan
recibos. Una reparación debe responder a fallo público real (o rechazo
intermedio vigente en T) y cambiar código Python/argv antes de medir por segunda
vez. Máximo dos mediciones públicas, sin repetir para elegir la mejor.

La revisión final ocurre una vez por entrega generada completa, en la familia
opuesta, sobre contrato, proceso, archivos y pruebas públicas. No habilita otra
reparación. Fallos de generación conservan artefactos parciales y revisión final
faltante; sus archivos pueden evaluarse funcionalmente después, sin reanudar
generación. No entregar tests/esperados/resultados reservados a autores/revisores.

Autor y revisor tienen contenedores/inputs separados. Sus perfiles primarios se
montan en su ubicación original, sin copias ni intercambio de autenticación.
El evaluador funcional usa otro proceso/imagen sin perfiles y un ID opaco sin
método/ledger. No afirmar aislamiento contra un cliente nativo malicioso o un
host operador que pueda alterar journals. Las revisiones de adherencia ven proceso.

## Límites y regla de parada aún por cerrar

Techos comunes propuestos:40 llamadas nativas por celda, incluida revisión final;
180s por llamada;6000s globales;128000 bytes por prompt realmente renderizado;
2MiB por stream;20000 bytes codificados de archivos;54000 bytes codificados de
documentos de proceso;4000 bytes codificados por stream que se devuelve como
contexto. Docker:1GiB/2CPU/128pids, root readonly y no-new-privileges. Tests públicos
120s, reservados3s. El presupuesto acumulado propuesto es3MiB por celda. Las
propuestas de1MiB y2MiB no admitieron la fixture completa de fases permitidas;
sus rechazos se conservan antes de cualquier generación. La fixture cabe en3MiB,
sin garantizar que cualquier respuesta nativa posible complete el método.

La campaña máxima será la suma de28 techos, sin ampliar tras observar resultados.
No acumular presupuesto no usado por otro método ni descontar revisiones del
coste de T. Una llamada fallida consume su admisión. Un recibo cerrado se puede
releer sin gastar otra llamada; una ejecución incierta se reconcilia sin reiniciar.

Un error terminal de generación cierra esa celda; pasar a la siguiente sólo
según el orden fijo. Una negativa de autenticación/cuota detiene nuevos envíos
de campaña y conserva las restantes no iniciadas. No cambiar cuenta, comprar
créditos, forzar reset ni aprovechar otra máquina como cuota distinta. La
consulta actual de cuota es evidencia previa, nunca garantía de terminar.

El gate distingue fallo terminal de celda y pausa sin admisión por cuota vieja
o agotada. Un fallo nativo real no clasificable como formato controlado detiene
la campaña sin reanudación automática. Eso puede dejar filas no iniciadas; no
se cubren con otra cuenta. La CLI exige revisión conjunta aceptada y fuentes
prerregistradas, todavía inexistentes. No interpretar exit0
del cliente o ausencia de error visible como review/phase/study aceptada.

## Medición y cierre

Usar la rúbrica pública separada por dimensión. Publicar28 filas previstas,
con estados no_iniciada, generación_fallida, entrega_incompleta, evaluada o
infra_inconclusa; no eliminar filas adversas. Mostrar por tarea/familia/repetición
las diferencias N/S/T y T/A, medias/rangos descriptivos y denominadores. No
realizar selección de mejor réplica, inferencia causal universal ni ranking
basado en adherencia de guías con denominadores diferentes.

El driver reservado sólo admite medición después de cerrar toda la generación
o de una parada terminal real de infraestructura; nunca durante una celda pendiente.
Cada invocación incierta queda inconclusa con su ID original, sin sustituirla.
Los ejemplos se ejecutan mediante recetas públicas fijas; la correspondencia de
los comandos del README se juzga con localizadores en la revisión independiente,
sin ejecutar shell arbitrario del documento. D3/D4 requieren ambas evidencias.

Registrar llamadas, tiempos, bytes renderizados, tests y native usage reportado.
Tokens faltantes, dinero y capacidad no observada quedan desconocidos; no
convertir porcentajes de cuota a número de llamadas. Toda intervención de
ingeniería se conserva y ocurre antes de generar; después sólo las reglas
fijas de feedback público del harness permiten reparación del programa.

Cerrar la goal requiere además una nueva entrega T de nueve fases, instalación
limpia/versionada CLI/MCP, controles negativos/reanudación, archivos reproducibles
y publicación en la web existente. Un estudio adverso puede ser válido; una
campaña incompleta o sólo tests de infraestructura no cumplen ese cierre.
GOAL.md original y los30 inputs del piloto backup permanecen intactos. Los
intentos terminales LogLens/IntervalDesk se conservan y no entran en esta población.
