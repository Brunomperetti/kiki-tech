// Capability for a bounded CSV produced by the authenticated application.
// The integration boundary can recognize this exact anchor without allowing
// arbitrary blob links, external URLs or changes to the demo's network policy.
const permitted = new WeakMap<
  HTMLAnchorElement,
  { url: string; filename: string }
>();
export function isPermittedCsvDownload(anchor: HTMLAnchorElement) {
  const entry = permitted.get(anchor);
  return (
    !!entry && entry.url === anchor.href && entry.filename === anchor.download
  );
}
export function downloadReviewCsv(blob: Blob, filename: string) {
  if (
    !/^text\/csv(?:;|$)/i.test(blob.type) ||
    !blob.size ||
    blob.size > 10 * 1024 * 1024 ||
    !/^kiki-(ml|tn)-(all|no_match|pending)\.csv$/.test(filename)
  )
    throw new Error("CSV o nombre de descarga fuera del contrato permitido.");
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  permitted.set(anchor, { url, filename });
  document.body.appendChild(anchor);
  try {
    anchor.click();
  } finally {
    anchor.remove();
    permitted.delete(anchor);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
