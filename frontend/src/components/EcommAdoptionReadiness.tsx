import type {EcommAdoptionPlan} from '../types/ecomm-app';

const gateText=(status:EcommAdoptionPlan['gates'][number]['status'])=>
  status==='PASS'?'Verificado':status==='BLOCKED'?'Revisión necesaria':'Pendiente de validar';

export function EcommAdoptionReadiness({plan}:{plan:EcommAdoptionPlan}){
  return <section className="kiki-ecomm-adoption" aria-label="Plan de incorporación del catálogo Ecomm">
    <header className="kiki-ecomm-adoption-heading">
      <div>
        <h4>¿Podemos empezar a usar la API como inventario principal?</h4>
        <p><strong>Todavía no.</strong> Ya tenemos gran parte de los productos identificados por su ID, pero falta resolver excepciones y asegurar que no perdamos precios ni vínculos comerciales.</p>
      </div>
      <span>Solo diagnóstico</span>
    </header>
    <div className="kiki-ecomm-adoption-counts">
      <div><strong>{plan.mapped_by_stable_id}</strong><small>Identificados por ID (sin activarlos)</small></div>
      <div><strong>{plan.mapped_with_identical_sku}</strong><small>Conservan ID y SKU exactos</small></div>
      <div><strong>{plan.mapped_with_format_difference}</strong><small>Mismo ID, escritura diferente</small></div>
    </div>
    <h5>Qué falta resolver</h5>
    <div className="kiki-ecomm-adoption-tasks">
      {plan.tasks.map(task=><article key={task.key} className="kiki-ecomm-adoption-task">
        <div className="kiki-ecomm-adoption-task-head">
          <strong>{task.title}</strong>
          <span>{task.count} {task.priority==='DONE'?'· Sin pendientes':task.priority==='INFO'?'· Informativo':''}</span>
        </div>
        <p>{task.description}</p>
        {task.key==='API_ONLY'&&<small>Dentro de este grupo: {task.combo_yes??0} combos confirmados, {task.combo_no??0} no combos y {task.combo_unknown??0} sin dato de combo.</small>}
        {task.count>0&&<small><strong>Dónde revisarlo:</strong> {task.review}</small>}
      </article>)}
    </div>
    <details className="kiki-ecomm-adoption-gates">
      <summary>Ver los controles pendientes antes de reemplazar el Excel</summary>
      {plan.gates.map(gate=><div key={gate.key} className="kiki-ecomm-adoption-gate">
        <div><strong>{gate.title}</strong><span>{gateText(gate.status)}</span></div>
        <p>{gate.reason}</p>
      </div>)}
    </details>
    <p className="kiki-ecomm-adoption-footnote">{plan.note}</p>
  </section>;
}
