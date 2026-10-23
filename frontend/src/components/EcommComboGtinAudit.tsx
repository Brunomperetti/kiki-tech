import type { EcommMlBrandEvidence } from '../types/ecomm-app';

type ComboAudit = EcommMlBrandEvidence['combo_gtin_audit'];

const categoryLabel:Record<string,string>={
  COMBO_SKU_WITH_NONCOMBO_GTIN_OWNER:'La variante del SKU es combo; algún propietario del GTIN no lo es',
  COMBO_SKU_COMPONENTS_UNKNOWN:'La variante del SKU es combo, pero no hay componentes identificados',
  NONCOMBO_SKU_GTIN_HAS_COMBO_OWNER:'La variante del SKU no es combo; alguno de los propietarios del GTIN sí',
  SKU_NOT_FLAGGED_COMBO:'La variante del SKU no está marcada como combo',
  SKU_COMBO_FLAG_UNKNOWN:'No hay dato verificable de combo para la variante del SKU',
};
const boolLabel=(value:boolean|null)=>value===true?'Sí':value===false?'No':'Sin dato';

export function EcommComboGtinAudit({audit}:{audit:ComboAudit}){
  const c=audit.counts;
  return <details className="kiki-ecomm-ml-blockers">
    <summary>Auditar combos y GTIN: separar hipótesis de componentes de datos comprobados</summary>
    <p>KIKI revisa los casos donde el SKU de Mercado Libre identifica una ficha Ecomm pero el GTIN apunta a otras fichas. Puede mostrar qué productos están marcados como combo, sin adivinar qué contiene cada pack.</p>
    <div className="kiki-ecomm-commercial-metrics">
      <div><strong>{c.contradictory_ml_rows}</strong><small>Filas ML con identidad contradictoria analizadas</small></div>
      <div><strong>{c.distinct_sku_gtin_cases}</strong><small>Casos SKU y GTIN distintos, agrupados</small></div>
      <div><strong>{c.distinct_sku_ids}</strong><small>Fichas Ecomm diferentes identificadas por SKU</small></div>
      <div><strong>{c.distinct_gtins}</strong><small>GTIN diferentes involucrados</small></div>
      <div><strong>{c.sku_variant_combo_yes_rows}</strong><small>Filas cuyo SKU apunta a una variante marcada combo</small></div>
      <div><strong>{c.sku_variant_combo_no_rows}</strong><small>Filas cuyo SKU apunta a una variante que no es combo</small></div>
      <div><strong>{c.sku_variant_combo_unknown_rows}</strong><small>Filas sin indicador de combo verificable</small></div>
      <div><strong>{c.possible_combo_component_pattern_rows}</strong><small>Patrón posible: SKU combo y dueño GTIN no combo</small></div>
      <div><strong>{c.numeric_family_hint_rows}</strong><small>Filas con pista de familia comercial numérica</small></div>
    </div>
    <p>Entre las filas, {c.gtin_has_noncombo_owner_rows} tienen algún dueño del GTIN no marcado como combo; {c.gtin_has_combo_owner_rows} tienen algún dueño marcado combo. Las causas se pueden superponer. {c.sku_outside_gtin_owners_rows} filas tienen SKU fuera de los propietarios del GTIN y {c.mla_reference_conflict_rows} tienen referencia MLA histórica contradictoria.</p>
    <p className="kiki-ecomm-hint"><strong>La API de inventario no proporciona composición de packs.</strong> Un GTIN repetido y una variante marcada combo no prueban que el otro producto sea su componente. Ninguna relación ni marca se modifica.</p>
    <details>
      <summary>Investigar casos concretos ({audit.examples.length} ejemplos de {c.distinct_sku_gtin_cases} casos)</summary>
      {audit.examples.length===0?<p>No hay casos de SKU/GTIN contradictorio con los datos actuales. No se inventaron relaciones con componentes.</p>:audit.examples.map((x,i)=><article className="kiki-ecomm-commercial-row" key={x.ecomm_id_by_sku+'-'+x.gtin+'-'+i}>
        <strong>SKU {x.ecomm_sku||'No informado'} · Ecomm ID {x.ecomm_id_by_sku}</strong>
        <small>{x.ecomm_name||'Sin título histórico'} · Variante marcada combo: {boolLabel(x.ecomm_variant_is_combo)} · Producto padre marcado combo: {boolLabel(x.ecomm_parent_is_combo)}</small>
        <p>{categoryLabel[x.category]}</p>
        <small>GTIN en publicaciones: {x.gtin} · {x.gtin_owner_count} fichas Ecomm asociadas · SKU Ecomm API GTIN: {x.ecomm_api_gtin||'No informado'}</small>
        <small>Publicaciones ML: {x.mla_count} ({x.mlas.join(', ')}) · {x.numeric_sku_family_hint?'Hay una pista numérica de familia comercial, sin validar componentes.':'Sin coincidencia de familia numérica comprobada.'}</small>
        {x.ml_titles.length>0&&<small>Ejemplo ML: {x.ml_titles[0]}</small>}
        <details>
          <summary>¿A qué fichas corresponde el GTIN? ({x.gtin_owner_count} IDs, hasta 8 mostrados)</summary>
          {x.gtin_owners.map(owner=><div key={owner.ecomm_id}>
            <small>ID {owner.ecomm_id} · SKU {owner.sku||'Sin SKU estable'} · {owner.name||'Sin nombre histórico'}</small>
            <small>Variante combo: {boolLabel(owner.variant_is_combo)} · Padre combo: {boolLabel(owner.parent_is_combo)} · GTIN informado por API: {owner.api_gtin||'No informado'} · Familia SKU: {owner.family_rule||'Sin regla numérica'}</small>
          </div>)}
          <p>Los propietarios del GTIN son referencias del Excel histórico. Ninguno está confirmado como componente de este SKU.</p>
        </details>
        <small>Motivos: {x.reason_codes.join(', ')} · Sin aprobación ni cambios de inventario.</small>
      </article>)}
    </details>
    <p>{audit.next_step}</p>
    <p className="kiki-ecomm-hint">{audit.policy}</p>
  </details>;
}
