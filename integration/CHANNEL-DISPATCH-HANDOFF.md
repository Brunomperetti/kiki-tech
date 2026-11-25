# KIKI 2.0 — continuación de publicación por canal

PR #225. Prioridad inmediata: Tiendanube y Mercado Libre. Etapas 4–6 independientes, recuperar primero el trabajo previo de Codex si existe. No asumir que está persistido.

## Implementado en esta rama
- Cliente Tiendanube aislado: backend/app/integrations/tiendanube/client.py.
- Previews locales por Ecomm ID exacto: services/tiendanube_publication_preview.py y mercadolibre_publication_preview.py; endpoints autenticados en commercial_exports.py.
- UI en ChannelsPanel.tsx: TiendanubePreviewPanel y MercadoLibrePreviewPanel. No hay envío real; controles deshabilitados.
- Registro compartido: channel_dispatch_storage.py y channel_dispatch.py, con restricciones únicas por tienda/canal/SKU e identidad, transiciones CAS y persistencia de incertidumbre. Pruebas SQLite iniciales; falta PostgreSQL 18 y migración explícita.
- Reutilizar prepublication_metadata_service.py, prepublication_image_service.py, final_publication_queue_service.py y cliente ML existente sin transferir aprobaciones por SKU ni usar capturas Ecomm XLSX.

## Siguiente trabajo, ordenado
1. Verificar contrato vigente en documentación oficial de cada API antes de conectar: versión, autenticación, permisos, formatos, categorías, atributos, identidad de vendedor y requisitos comerciales. No asumir que la primitiva TN actual es compatible sin pruebas de contrato. Confirmar específicamente semántica de ocultamiento y respuesta. No usar secretos reales en pruebas.
2. Revisar seguridad del contenido, duplicados, revisión de evidencia, versión y huella del preview; comprobar que cualquier cambio posterior invalida la autorización. Validar GTIN, unidad/pack y vínculo exacto por Ecomm ID. No fingir derechos sobre imágenes ni rellenar campos inventados.
3. Diseñar migración aditiva y reversible del registro, pruebas PG18 concurrentes, reserva y compare-and-swap, límites de tiempo, recuperación por consulta remota con evidencia inequívoca. No reintentar escrituras inciertas, ni reutilizar la reserva como autorización indefinida. Diseñar cancelación segura antes de envío y reconciliación manual auditada. No ejecutar DDL en producción automáticamente.
4. Tiendanube: credencial privada en backend, flags independientes default-off, verificar tienda y permiso; lectura remota completa y detección de duplicados; piloto de una sola variante oculta, verificación posterior de identidad y estado, sin modificar precio/stock ni habilitar ventas. Imágenes, taxonomía oficial, variantes agrupadas y SEO según contrato real. Si ocultamiento no es garantizable, bloquear.
5. Mercado Libre: verificar OAuth vigente y vendedor; resolver requisitos actuales de modalidad de publicación, categoría, atributos obligatorios/condicionales, fotos, condiciones de venta, moneda, precio y cantidad. Consultar/validar oficialmente sin crear una publicación; no usar precios o stock ficticios. Adaptar flujo anterior por identidad exacta. Crear solo tras aprobación específica y validación oficial de payload; no asumir que puede crearse oculto.
6. Pruebas de endpoints autenticados, CSRF, flags, store/account mismatch, permisos, errores de proveedor, estado incierto, múltiples sesiones, revocación de evidencia, cambio de preview y Playwright para ambos paneles. CI 4/4 del head exacto y revisión humana antes de merge.
7. Despliegue y migración por autorizaciones separadas. Piloto real solo con permiso explícito del operador y producto aprobado. No habilitar escrituras masivas. Registrar ID remoto y estado comprobado.

## Restricciones
Ecomm-App exclusivamente API. No alterar precios/stock de origen. No tocar secretos, variables, BD productiva, proveedores, servicios pagos ni publicaciones reales sin autorización explícita. No declarar integración finalizada por previsualización o CI. Natural Seed 7518949 sigue bloqueado hasta evidencias y derechos válidos. La API OpenAI tenía HTTP401; no suponer habilitada. No consumir IA en pruebas.

## Definition of done
Fichas y evidencia coherentes, validaciones del proveedor reales y separadas de las locales, protección de duplicados y recuperación comprobada, PR revisada, CI verde, migración revisada, piloto autorizado con identificador remoto y verificación posterior. Aceptación de los dueños de KIKI antes de habilitar publicación masiva.
