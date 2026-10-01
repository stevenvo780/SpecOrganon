# D122 — propuesta revisable de ruta R1, sin ejecución

## Registro prospectivo

Base: `9f90b79b75c087ea5e9c6ab87f270880e7fb684a` (D121). GOAL leído
íntegramente. C1 técnico D107; C2–C5 No demostrado; 0/24 celdas formales.
El siguiente avance de aceptación requiere resultados reales, no más fixtures.

Esta unidad prepara decisiones concretas para las doce celdas R1, sin llamadas
a proveedor, lectura de credenciales, apertura de reserva, campo o publicación.
No es el freeze experimental autorizado y no cuenta como R1.

## Trabajo y ownership

1. Root conserva GOAL, protocolo y fuentes/casos/contratos históricos; registra
   tarifas actuales desde páginas oficiales y sus condiciones. No atribuye
   a la presencia de un CLI ni a su cuota acceso a Responses API.
2. Worker nativo de implementación posee únicamente `candidates/` y
   `forecast.json`: dos alternativas de modelo (`gpt-6-astra`, `gpt-6-luna`),
   esfuerzo `high`, la misma semilla/recursos/roles y cálculo entero en microUSD.
   Son opciones; sólo una podrá seleccionarse para doce R1. No son 24 runs.
3. Root posee los demás archivos del dossier y docs activos. Invoca el
   preparador D118 original para build/verify de ambas opciones bajo los dos
   intérpretes exactos registrados. Retiene comandos, exit codes, stdout/stderr,
   inventarios y calendarios; no prepara ni libera runtimes de ejecución.
4. Revisor independiente audita fuentes, aritmética, comparabilidad, cobertura
   de calendarios y límites antes de cualquier petición de autorización.

Máximo tres ramas concurrentes; sin escritores compartidos. El worker no
revierte cambios ajenos. Luna ya realizó lectura acotada de compatibilidad.

## Valores propuestos

- R1: A/B/C × D-F/D-E × dos repeticiones = doce celdas; orden con seed 122.
- Por celda, saldo común de todos los roles: 80.000 tokens medidos, 128
  solicitudes, 64 tools y 5.400 segundos activos. No confundir actividad con W.
- Cada rol: output máximo 8.192; líder/workers hasta 32 turnos, reviewer uno.
  Máximo ocho épocas; tools hasta 30 segundos. Son propuestas, no evidencia de
  suficiencia. Conservar el riesgo de truncamiento de razonamiento `high`.
- Route OpenAI Responses v1, service tier `default`, tarifas Standard de texto
  y contexto corto; sin afirmar versión de snapshot ni acceso de cuenta.
- Coste local propuesto: Astra USD 5/celda (USD 60 R1), Luna USD 0,05/celda
  (USD 0,60 R1). Ninguno está autorizado. El techo de tokens debe calcularse
  aparte de esos saldos, incluyendo redondeo por solicitud.

## Verificación proporcional y rechazo

- Usar los comandos originales build/verify; cada calendario debe tener doce
  identidades nuevas y exactamente cuatro bloques de tres alternativas.
- Mismos casos/contratos/información/acceso/límites/orden entre opciones; sólo
  identidad del modelo, tarifas, saldo de coste e identificadores derivados
  podrán cambiar. Verificar ambos Python 3.11 y 3.12, sin repetir runtimes.
- Preservar fuentes e inventarios históricos. No llamar `step`, `release`,
  `send`, conteo remoto ni proveedores. No presentar preparación como run.
- Forecast limitado a modelo bajo las condiciones de tarifa verificadas;
  herramientas, impuestos, regionalización, evaluación y H no se inventan ni
  se imputan cero. El saldo local no acredita factura ni límite remoto.
- Alias publicado en `version` es una declaración, no versión servida fijada.
  Registrar los gaps de acceso/transporte, identidad real, esfuerzo efectivo,
  conteo/uso, respuesta incomplete, capacidad y evaluación independiente.
- Ruff/sintaxis/diff sobre scripts nuevos si los hay; no suite histórica ni
  tests que sólo repitan documentos. Revisor recalcula cifras y usa los
  verificadores reales del preparador.

## Cierre

Guardar configuración, evidencia local y veredicto limitado. Actualizar docs
activos sólo después de capturas, conservando cortes históricos. Commit con
pathspec explícito; sin push. Presentar al dueño la opción concreta y las
decisiones/acceso/autorización pendientes. GOAL permanece activo e incompleto.
