# MVP de SpecOrganon

## Prioridad acordada · 2026-10-01

La prioridad inmediata es una evolución operativa de SDD que incorpore
filosofía, ciencia e ingeniería. Primero construiremos y usaremos un mínimo
viable con proyectos que podamos manejar entre el dueño y los agentes,
aprovechando las herramientas y suscripciones presentes. La aplicación a
problemas con financiación y las evaluaciones finales vendrán después.

Este hito ordena el desarrollo; no modifica [GOAL.md](../GOAL.md), los
resultados anteriores ni los criterios de un ensayo ya registrado. El MVP
puede tener valor de uso antes de demostrar superioridad frente a SDD o
eficacia de una intervención alimentaria.

## Qué debe poder hacer

Un agente recibe un encargo acotado, investiga el problema, compara
soluciones, construye una intervención local y comprueba sus resultados.
Conserva el contexto para reanudar y corrige las decisiones afectadas cuando
cambia una premisa. El dueño define el propósito y los límites; las tareas
técnicas se ejecutan y revisan con los agentes disponibles.

| Frente | Trabajo mínimo | Resultado utilizable |
| --- | --- | --- |
| Filosofía | Delimitar problema, actores, conceptos, supuestos, fines y conflictos. | Encargo claro y compromisos explícitos; decisiones normativas relevantes aprobadas. |
| Ciencia | Formular hipótesis, elegir una comparación, recoger datos accesibles y conservar resultados negativos. | Evidencia reproducible, inferencias y límites separados. |
| Ingeniería y SDD | Comparar al menos dos alternativas, derivar requisitos y criterios antes de implementar. | Solución local ejecutable y trazabilidad de sus decisiones. |
| Validación | Ejecutar pruebas y contrastar el resultado con la línea base y los criterios previos. | Veredicto acotado sobre el proyecto y revisión de otro agente o verificación objetiva. |

La ciencia en un proyecto local puede usar experimentos de software,
archivos disponibles y mediciones reproducibles. Una prueba de software
justifica una afirmación sobre ese software; los proyectos materiales
necesitarán sus propias observaciones.

## Recursos y primer proyecto

Usaremos la sesión de Codex, sus subagentes nativos, la CLI y MCP locales y
los datos ya disponibles. Esta ruta no exige contratar una API adicional ni
completar el panel de jueces del estudio confirmatorio.

El primer proyecto es la propia entrada de uso de SpecOrganon: permitir que
un agente y su dueño inicien un caso local y entiendan qué hacer, qué quedó
pendiente y cómo continuar. Sus resultados se observan en este repositorio
con comandos reales. Después aplicaremos el mismo recorrido a un segundo
proyecto local acotado; ambos serán casos de desarrollo expuestos.

Haremos como máximo dos rondas de mejora de ese recorrido antes de emitir
un veredicto del hito. Cada ronda conserva sus errores y termina con una
solución comprobada o un pendiente concreto. Ninguna ronda requiere abrir
los casos reservados de la evaluación final.

## Criterios del hito

Estos criterios se fijan para el trabajo siguiente; no son pruebas ya
aprobadas.

1. Una entrada de uso explica cómo iniciar un caso con un agente nativo,
   sin API adicional, y qué funciones ejecuta el toolkit.
2. Un proyecto local produce un resultado útil mediante los cuatro frentes,
   con alternativas, criterios previos y evidencia real de ejecución.
3. Un requisito seleccionado puede rastrearse hasta problema, compromisos y
   evidencia; una premisa revisada invalida sus dependencias.
4. Otro agente revisa el resultado técnico o un verificador objetivo lo
   contrasta. Se conservan sus hallazgos y las correcciones.
5. Se interrumpe y reanuda el trabajo sin perder contexto ni duplicar
   artefactos; se entrega una instrucción reproducible de uso.
6. El informe distingue resultado local, limitaciones y pendientes de la
   validación final. Las decisiones normativas y las acciones que excedan el
   encargo conservan la autorización requerida.

El MVP estará listo cuando este recorrido sea usable y esté comprobado.
Su lanzamiento será una versión inicial con ese alcance declarado.

## Entrada local disponible hoy

Desde la raíz del repositorio, con las dependencias instaladas:

```sh
uv run organon init ./mi-caso-mvp --title "Entrada local de SpecOrganon" --domain desarrollo --actor agent:analista
uv run organon put ./mi-caso-mvp p1 --kind problem --text "Un agente necesita iniciar un caso local y entender el siguiente trabajo y sus bloqueos." --actor agent:analista
uv run organon put ./mi-caso-mvp a1 --kind actor --text "El dueño fija el encargo; el agente ejecuta; otro agente revisa los resultados técnicos." --ref p1 --actor agent:analista
uv run organon put ./mi-caso-mvp b1 --kind boundary --text "CLI y archivos locales de desarrollo; herramientas y suscripciones presentes." --ref p1 --actor agent:analista
uv run organon next-task ./mi-caso-mvp
uv run organon status ./mi-caso-mvp
uv run organon trace ./mi-caso-mvp p1
```

Estos comandos crean artefactos reales del encargo. No completan todavía las
nueve fases ni aportan resultados experimentales. El nombre de directorio
debe estar libre para iniciar un caso nuevo.

Encargo para el agente:

> Trabaja este caso con filosofía, ciencia, ingeniería y validación. Usa
> herramientas locales y los recursos actuales. Antes de implementar,
> conserva la línea base y define criterios observables. Compara dos
> alternativas, ejecuta la solución y pide una revisión técnica separada.
> Registra evidencias y dependencias, corrige los hallazgos y deja el trabajo
> reanudable. Presenta para decisión los compromisos normativos relevantes.

El agente aporta el razonamiento, opera las herramientas y ejecuta las
pruebas. El runner conserva los pasos declarados y comprueba compuertas; no
genera investigación ni lanza por sí solo agentes o pruebas.

## Qué falta cerrar

- Conectar esa entrada con un proyecto completo y una entrega utilizable.
- Simplificar la configuración y la reanudación de la revisión técnica.
  Actualmente los casos reales usan `signed`: aceptar fases y reportar
  pruebas requiere un registro y firmas válidas. Una revisión de subagente
  es evidencia técnica, pero no satisface automáticamente esas compuertas.
  Resolver esta integración es trabajo del MVP, no una razón para detener
  la investigación y los borradores locales.
- Comprobar el recorrido, su interrupción y la revisión de dependencias con
  el proyecto elegido, y preparar una guía breve para el siguiente usuario.

La demostración causal alimentaria, la comparación confirmatoria de
modelos/métodos y la transferencia final siguen pendientes bajo sus
criterios originales. La siguiente actividad del MVP se elige por utilidad
local, sin exigir primero la financiación de esos estudios.
