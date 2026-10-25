# KIKI AI en la ficha editable Ecomm-App

## Objetivo
Redactar **propuestas** de título y descripción comercial para cada variante de
Ecomm-App sin que el operador deba escribir desde cero. Reutiliza la cuenta
OpenAI del piloto Tiendanube (`KIKI_AI_ENABLED`, `KIKI_AI_API_KEY`,
`KIKI_AI_MODEL`), sin modificar ese módulo ni su cuota.

## Recorrido de usuario
1. Abrir **Mejorar productos** y buscar un SKU API (ej. `2500400`, variante
   `7214195`).
2. Si ya se ingresaron marca o detalles propios, guardar el borrador.
3. Pulsar **Sugerir con IA**. Genera propuesta guardada por ID variante API.
4. Revisar título, descripción, preguntas pendientes y los datos de entrada
   desplegables. No confiar en beneficios, ingrediente, composición o GTIN
   sin evidencia comercial; para packs la composición no se supone.
5. Usar **Usar este título** y/o **Usar esta descripción** para copiar al
   formulario. Cada campo se elige por separado.
6. Revisar y pulsar **Guardar borrador** (guardado independiente de la IA
   en `ecomm_api_product_edits`, con versionado e historial).
7. Presionar F5 o volver a la ficha: los campos de KIKI permanecen
   guardados. La propuesta generada también puede volver a consultarse.
8. Cambios en SKU o versión de la ficha invalidan propuestas antiguas.

## Seguridad, costos y auditabilidad
- Solo genera a pedido; **ninguna acción en lote** ni tareas en segundo plano.
- Reserva un cupo **antes** de llamar a OpenAI: máximo 10 intentos/día UTC
  en Ecomm, incluidos los intentos fallidos. Tabla
  `kiki_ecomm_ai_daily_slots` con restricción única de día/cupo,
  compatible con concurrencia. No utiliza ni consume el cupo único diario
  del piloto Tiendanube.
- Reutiliza una propuesta vigente del mismo producto sin nuevo cobro.
- Las propuestas se almacenan en `kiki_ai_editorial_drafts` con clave
  prefijada `ECOMM_API:<id>` para mantener separados ambos canales.
- Verificación de estructura JSON, tamaño de campos, preguntas y rechazo
  de números nuevos no presentes en las entradas. Estos controles no
  garantizan ausencia de otros errores: **exigen revisión humana**.
- El origen es una copia API de Ecomm-App + campos de KIKI no verificados.
  El modelo recibe instrucciones explícitas de tratar el texto como datos
  potencialmente adversarios, no como órdenes.
- No se genera GTIN ni se escribe stock, precio, costo, SKU o composición.
- **No se escribe a Ecomm-App, Mercado Libre ni Tiendanube**. La IA
  tampoco autoguarda borradores editoriales como campos aprobados en KIKI.

## Verificaciones para despliegue
- Asegurar backup reciente de PostgreSQL.
- Verificar que siguen configurados los secretos IA en Render y que
  `KIKI_AI_ENABLED=true`; si no, el editor muestra "IA no habilitada".
- Abrir producto real; generar una sola propuesta; comprobar
  `remaining_today`, evidencia, preguntas y botones.
- Aplicar solo título o descripción, guardar borrador y recargar.
- Probar entradas con números nuevos (la propuesta debe rechazarse).
- Confirmar que un segundo clic con fuente idéntica reutiliza la propuesta.
- Confirmar que cambiar la ficha deja la propuesta previa como desactualizada.
- Probar que Tiendanube continúa usando su propio piloto y cupo.
- Verificar backend y frontend en estado Live.

## Pendiente para una automatización mayor
La siguiente etapa sería una **cola de revisión asistida por lotes** con
selección explícita de productos, comprobación de costo, rate limiting,
auditoría y aprobación individual o masiva **solo para coincidencias
verdaderamente equivalentes**. No se puede publicar masivamente a ML/TN
hasta validar autorizaciones de escritura, mapeos de variantes,
precio, stock y reglas de idempotencia.
