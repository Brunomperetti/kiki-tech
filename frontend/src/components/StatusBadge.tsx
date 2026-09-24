import type {Status} from '../types/catalog';
const labels:Record<Status,string>={ALREADY_PUBLISHED:'Ya publicado',CANDIDATE_TO_PUBLISH:'Candidato',REVIEW_REQUIRED:'Revisar',POSSIBLE_DUPLICATE:'Posible duplicado',INCOMPLETE_DATA:'Datos incompletos',INVALID_SKU:'SKU inválido',INVALID_EAN:'EAN inválido',UNMATCHED_ML_LISTING:'Publicación sin asociar'};
export const StatusBadge=({status}:{status:Status})=><span className={`badge ${status}`}>{labels[status]}</span>;
