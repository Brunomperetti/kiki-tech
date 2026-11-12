import { environmentText } from "./runtime";
import { useEffect, useRef, useState } from "react";
import { request, captureDate, validVariantId } from "./catalog-adapter";
type Saved = {
  saved_in: string;
  external_writes_enabled: boolean;
  page: number;
  limit: number;
  total: number;
  items: {
    ecomm_id: string;
    title: string;
    product_name: string;
    version: number;
    updated_at: string;
    status: string;
  }[];
};
export function SavedHistory({
  onClose,
  onOpen,
}: {
  onClose: () => void;
  onOpen: (id: string) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null),
    [page, setPage] = useState(1),
    [data, setData] = useState<Saved>(),
    [error, setError] = useState("");
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  useEffect(() => {
    const c = new AbortController();
    setError("");
    setData(undefined);
    request(`/api/ecomm-app/workspace/saved?page=${page}&limit=10`, {
      signal: c.signal,
    })
      .then((r) => r.json())
      .then((v: Saved) => {
        if (
          v.saved_in !== "KIKI_POSTGRESQL_INTERNAL_ONLY" ||
          v.external_writes_enabled !== false ||
          v.page !== page ||
          v.limit !== 10 ||
          !Number.isSafeInteger(v.total) ||
          v.total < 0 ||
          !Array.isArray(v.items) ||
          v.items.length > 10 ||
          new Set(v.items.map((x) => x.ecomm_id)).size !== v.items.length ||
          v.items.some((x) => !validVariantId(x.ecomm_id))
        )
          throw new Error(
            "Historial incompatible con las identidades del catálogo.",
          );
        if (!c.signal.aborted) setData(v);
      })
      .catch((e) => {
        if (!c.signal.aborted) setError(e.message);
      });
    return () => c.abort();
  }, [page]);
  return (
    <dialog
      className="s-settings"
      ref={ref}
      aria-label="Historial de fichas guardadas"
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
    >
      <h2>Historial de fichas guardadas</h2>
      <p>
        El mismo editor y sus versiones. Abrí una variante para revisar su
        historial completo.
      </p>
      {error && <p role="alert">{error}</p>}
      {data?.items.map((r) => (
        <p key={r.ecomm_id}>
          <strong>{r.title || r.product_name || r.ecomm_id}</strong>
          <br />
          Ecomm ID {r.ecomm_id} · Versión {r.version} ·{" "}
          {captureDate(r.updated_at)}
          <br />
          <button onClick={() => onOpen(r.ecomm_id)}>
            Ver historial {r.ecomm_id}
          </button>
        </p>
      ))}
      {data && !data.items.length && <p>Todavía no hay fichas guardadas.</p>}
      <div>
        <button disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
          Anterior
        </button>{" "}
        Página {page}{" "}
        <button
          disabled={!data || page * 10 >= data.total}
          onClick={() => setPage((p) => p + 1)}
        >
          Siguiente
        </button>
      </div>
      <p>
        <a
          href="/api/ecomm-app/workspace/master-export"
          download={environmentText(
            "fichas-kiki-pruebas.json",
            "fichas-kiki.json",
          )}
          data-kiki-download="master-export"
        >
          Descargar fichas guardadas · JSON
        </a>
      </p>
      <button onClick={onClose}>Volver a Mi catálogo</button>
    </dialog>
  );
}
