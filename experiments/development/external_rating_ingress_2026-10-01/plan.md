# D124 — ingreso operativo de evaluaciones externas DEV

Registro previo sobre D123 `7d5a7762918b19ebd581e0499f0a6407568c50a2`.
GOAL leído íntegramente; el turno anterior produjo progreso verificado.
C1 técnico D107, C2–C5 No demostrado y0/24 formales. GOAL/protocolo/matriz,
casos, producción y fuentes/dossiers sellados permanecen intactos.

## Propósito y alcance

Hacer utilizable la entrada de notas externas pendiente tras D123. Integrar
el borrador aislado, añadir un comando de lectura de originales privados y
conservar los ensayos, fuentes, negativos y revisión independiente. No asignar
notas, no tratar declaraciones de independencia/custodia como prueba y no
confundir suma aritmética con Q verificada. No abrir reserva o campo, leer
credenciales, usar API experimental pagada ni publicar hacia afuera.

El borrador previo se conserva con su planSHA
`d33b76613e928aca78dce0f3adbb5f76b52e5fb0e703b7eb7c4e511e98bbe41e`
en `/tmp/specorganon-D124-staging-ffv4ct0l`. Su primera captura informa
69pruebas por intérprete, sin integración/revisión de root aún; no reemplaza
los gates de esta unidad.

## Contrato y ownership

- Worker: `scripts/development_rating_ingress.py` y
  `tests/test_development_rating_ingress.py`, desde bytes originales del
  borrador. API pura, bytes+SHA exactos, JSON cerrado, cinco enteros0..20 y
  seis tipos críticos fijados por rúbrica D118. No rescribir raw; reporte
  allowlist sin identificadores/textos privados. Suma denominada
  `declared_component_total`; verificaciones humanas/Q/aceptación false.
- Root: `scripts/read_development_rating.py`, su test, dossier/capturas/sello
  y cuatro docs activos después de las capturas. CLI readonly con ficheros
  privados acotados/singlelink/nofollow y bindings de SHA suministrados;
  contratos públicos originales fijos. No crea juicio, autoridad o registro
  externo, no modifica originales y no guarda una nota normalizada sustituta.
- Revisor independiente: sólo `review/`; valida código, efectos reales de CLI,
  bindings, sanitización, alcance de claims, archivos y conservación previa.

Máximo cuatro ramas contando root, profundidad dos y ownership disjunto.
Todos preservan cambios ajenos. Ruteo interno con cuota observada; calidad
no se infiere del coste o del nombre del modelo. No se aplican reglas del
panel confirmatorio de dos jueces/arbitraje como requisito inventado para DEV.

## Gates y evidencia

1. Antes de escribir código, este plan se guarda en Git. Borrador/handoff,
   fuentes y streams originales se conservan con límites explícitos.
2. Tests proporcionados de tipos/duplicados/tamper/errores/sanitización y
   lectura privada/noefectos. Ruff/sintaxis/diff y ambos Python exactos.
3. CLI real en ambos intérpretes sobre nuevos originales sintéticos: rating
   100 con incidente crítico visible; formato distinto con los mismos valores
   y hash distinto; declaración unknown; bindings/privacidad inválidos.
   Ningún control es juicio humano, caso real o celda formal. No consultar
   runtimes/modelos para fabricarle una nota al participante.
4. Freeze antes de gates finales, fuentes before/after, comandos/streams y
   originales archivados por bytes/modos. Preservación D123 antes/después;
   cuatro docs anteriores en Git sólo avanzan después de capturas.
5. Revisión independiente, recibo live/índice/HEAD y commit pathspec explícito,
   sin push. No repetir suite histórica/instalación/C1 ya verificados.

## Pendientes hacia GOAL

No hay evaluaciones humanas suministradas. Sigue pendiente su disponibilidad,
competencia/independencia, custodia/cegamiento/cronología verificable y control
de fuentes. Se consultó disponibilidad al dueño una vez; no hay polling ni
autorización por silencio. Siguen elección/acceso/gasto/modelo/telemetría reales,
H/costes completos. Luego12R1→adaptación/freeze→12R2/selección→confirmación
N/SDD/T con familias, capacidades, esfuerzos, agentes y ablaciones→campo
causal y transferencia real. Ningún test cambia ese veredicto.
