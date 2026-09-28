# Despacho medido de una solicitud de desarrollo

`scripts/run_managed_response.py` ofrece una ruta **de desarrollo** para una
solicitud de texto a OpenAI Responses. Usa el endpoint de
[conteo de entrada](https://developers.openai.com/api/docs/guides/token-counting)
antes del envío y fija `max_output_tokens`, que según la documentación de
OpenAI incluye salida visible y razonamiento. El ledger privado
`scripts/managed_token_ledger.py` reserva la suma antes de enviar, comparte
el tope entre roles que usan la misma carpeta y conserva la reserva cuando
el resultado es incierto.

## Contrato local

1. El operador crea **una sola** carpeta de ledger por corrida, fuera del
   workspace visible al modelo. Fija el máximo de tokens y de solicitudes.
2. Cada agente entrega un ID de solicitud único, su rol y un JSON con
   `model`, `input`, `max_output_tokens` y opcionalmente `instructions` y
   `reasoning: {"effort": "..."}`. El ejecutor rechaza herramientas y otros
   campos: todavía no coordina llamadas de herramienta ni conversaciones.
3. El transportador solicita al proveedor el conteo de esa entrada. El ledger
   reserva, bajo un lock entre procesos, entrada contada más el techo de salida. Si no cabe,
   no se llama a `/responses`. Solo puede quedar una solicitud pendiente a la
   vez por ledger; una muerte del proceso tras reservar impide enviar otra
   hasta revisar ese intento.
4. Tras el envío se guarda el JSON completo de respuesta en un archivo nuevo
   bajo una carpeta privada. Solo entonces se concilian
   `input_tokens + output_tokens = total_tokens`; el caché está incluido en
   entrada y el razonamiento en salida, sin volver a sumarlos.
5. Si el envío, la escritura o la telemetría fallan, la reserva queda retenida
   y el ledger impide otras solicitudes hasta revisión. No hay reintento
   automático. Una respuesta `incomplete` con uso válido se concilia y el
   orquestador puede enviar otra solicitud; la política del estudio debe decidir
   cuándo una corrida está truncada e impedir sustituirla por una favorable.

La preparación local no llama al proveedor:

```sh
python3 scripts/run_managed_response.py init /ruta/privada/corrida-01/ledger \
  --limit-tokens 80000 --max-requests 100
```

El subcomando `send` requiere `--allow-paid-request` y `OPENAI_API_KEY`, además
del ledger, JSON de solicitud, archivo nuevo de respuesta, ID y rol. **Esa
bandera no acredita autorización humana ni impone un límite de dólares.** No
se ejecutó `send` contra un proveedor para este desarrollo. Las pruebas usan
un transporte falso y un servidor HTTP local, sin gasto ni credenciales.

## Límite de la evidencia

Este control cubre únicamente las solicitudes que pasan por este ejecutor y
comparten el mismo ledger. Rechaza redirecciones HTTP con la clave adjunta.
La CLI opaca de `run_development_arm.py` sigue analizando uso al terminar y no
adopta este control. El ledger y la cuenta son
locales, sin custodia independiente ni recibo de factura. Faltan límite de
tiempo activo común, herramientas compartidas, tarifa y techo de gasto,
versiones exactas de modelo, agentes coordinados, familias adicionales,
reservas, jueces ciegos y evaluación de campo. Hasta integrar y verificar
esas condiciones, el piloto facturable y el criterio 4 continúan **NO-GO / no
demostrado**. El máximo de 80 000 tokens procede del
[protocolo prospectivo](protocolo_experimental.md#3-brazos-panel-y-comparabilidad);
no es por sí mismo una autorización para consumirlo.

Las pruebas de recuperación cubren muerte del proceso y reapertura local del
ledger. No ensayan apagón del host ni garantías del dispositivo de
almacenamiento; el journal tampoco tiene custodia externa frente a cambios del
mismo usuario.
