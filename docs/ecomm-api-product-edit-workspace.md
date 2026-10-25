# KIKI Tech — primera etapa operativa sobre Ecomm-App API

## Motivo
El cliente necesita editar datos en KIKI Tech, guardarlos y retomarlos más
adelante, sin depender de Excel ni esperar la reautorización de Mercado Libre.

## Fuente, identidad y alcance
- **Identidad**: ID estable de variante que existe **una sola vez** en la
  captura completa `ECOMM_APP_API_STAGE`, proveniente de la API de Ecomm-App.
- **Solo API Ecomm**: las rutas nuevas **nunca consultan el Excel
  `ECOMM_APP`** ni `ECOMM_APP_RAW`.
- **Campos editables**: marca, título comercial propuesto, descripción,
  GTIN propuesto y notas / evidencia.
- **No editables desde esta pantalla**: SKU o ID de origen, stock,
  precio, costo, flag de combo ni composición de los packs.
- Los datos se almacenan en una tabla PostgreSQL independiente
  `ecomm_api_product_edits`. No se cambia el snapshot original.
- Estatus: `DRAFT` y `READY_FOR_REVIEW`. Ambos son **internos**
  y **NO significan aprobado para vender, exportar ni publicar**.
- `inventario:leer` permite leer/consultar productos; **no permite escribir
  a Ecomm-App**. La cuenta ML sigue requiriendo autorización del dueño.
- Se puede efectuar verificación puntual de SKU/ID contra Ecomm-App
  mediante la consulta existente; no se modifica stock.

## Endpoints autenticados
- `GET /api/ecomm-app/workspace/saved?q=&status=&page=&limit=`:
  lista y métricas de fichas guardadas.
- `GET /api/ecomm-app/workspace/{ecomm_id}`: ficha editable junto con
  la información original y el historial.
- `POST /api/ecomm-app/workspace/{ecomm_id}`: edita la ficha con
  `expected_version`, `status` y `fields`, sesión y CSRF obligatorios.

Cada escritura conserva historial de cambios con campo, antes, después,
fecha y versión. Conflicto de versión da 409; no se sobrescribe una
edición de otra sesión. Un SKU que cambie bajo el mismo ID se bloquea.
El código GTIN propuesto se valida por longitud y dígito verificador;
su validez matemática **no** prueba correspondencia comercial.

## Demo funcional
1. Abrir `/workspace`, buscar SKU 2500400.
2. Abrir la variante API y comprobar ID, SKU y tipo combo.
3. Usar «Verificar este SKU en Ecomm-App ahora» si el servicio responde.
4. Completar una marca, título o descripción; guardar borrador.
5. Ir a otra sección y volver: seleccionar «Fichas guardadas» y
   reabrir el producto. Confirmar persistencia.
6. Editar de nuevo, comprobar historial y enviar a **revisión interna**.
7. Volver a abrir y comprobar nuevo estado.
8. No ejecutar publicaciones ni modificar el inventario externo.

## Desarrollo pendiente para completar el objetivo histórico
- Migrar módulos de tareas y enriquecimiento al ID de variante API;
  hoy coexisten flujos históricos basados en Excel separados en el menú.
- Obtener/verificar precios, costos, atributos e imágenes de fuentes
  autorizadas (la API Ecomm solo inventario no garantiza esos campos).
- Combos: conocer componentes y cantidades reales, no inferir por SKU.
- Aprobar datos comerciales y publicar en ML/TN mediante escritura
  idempotente, credenciales autorizadas y pruebas de reversión.
- Copias de seguridad de PostgreSQL tras la recuperación del plan Render.
- Usuarios/permisos multioperador, reportes de revisión/exportación y
  pruebas reales de extremo a extremo con Guillermo y Mercedes.

## Operación segura
El alta de la nueva tabla es aditiva: `Base.metadata.create_all` al iniciar
el backend. No se destruye ni migra contenido previo. **Antes de la demo
de producción se requiere probar Render Live y realizar backup**.
