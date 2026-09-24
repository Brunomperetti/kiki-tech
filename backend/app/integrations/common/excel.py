from dataclasses import dataclass, field
from io import BytesIO

import pandas as pd

from ...catalog.normalizer import normalize_title


class ExcelImportError(ValueError):
    pass


@dataclass
class ImportReport:
    records: list
    unknown_columns: list[str]
    mapped_columns: dict[str, str]
    rows_read: int
    rows_accepted: int
    rows_discarded: int
    header_row: int
    warnings: list[str] = field(default_factory=list)


class ExcelImporter:
    aliases: dict[str, set[str]] = {}
    required_any: set[str] = set()
    source_label = "archivo"

    def _mapping(self, columns) -> dict[str, str]:
        mapping: dict[str, str] = {}
        normalized_aliases = {
            target: {normalize_title(alias) for alias in names}
            for target, names in self.aliases.items()
        }
        for column in columns:
            normalized = normalize_title(column)
            for target, names in normalized_aliases.items():
                if normalized in names and target not in mapping:
                    mapping[target] = str(column)
        return mapping

    def _detect_header(self, raw: pd.DataFrame) -> tuple[int, dict[str, str]]:
        candidates: list[tuple[int, int, dict[str, str]]] = []
        # Header detection is entirely content-based; no row number is assumed.
        for index, row in raw.iterrows():
            mapping = self._mapping(row.tolist())
            if self.required_any.intersection(mapping):
                candidates.append((len(mapping), int(index), mapping))
        if not candidates:
            expected = ", ".join(sorted(self.required_any))
            raise ExcelImportError(
                f"No se encontró una fila de encabezados con columnas válidas "
                f"({expected}) en el archivo de {self.source_label}."
            )
        _, index, mapping = max(candidates, key=lambda item: (item[0], -item[1]))
        return index, mapping

    def read(self, content: bytes) -> ImportReport:
        try:
            raw = pd.read_excel(
                BytesIO(content), header=None, dtype=object, engine="openpyxl"
            )
        except Exception as exc:
            raise ExcelImportError(
                f"No se pudo leer el archivo {self.source_label}. Verificá que sea un XLSX válido."
            ) from exc

        header_index, _ = self._detect_header(raw)
        headers = [
            str(value).strip() if pd.notna(value) else ""
            for value in raw.iloc[header_index]
        ]
        frame = raw.iloc[header_index + 1 :].copy()
        frame.columns = headers
        frame = frame.dropna(axis=1, how="all")
        mapping = self._mapping(frame.columns)
        known = set(mapping.values())
        unknown = [str(column) for column in frame.columns if str(column) not in known]

        records = []
        discarded = 0
        for _, row in frame.iterrows():
            model = self.to_model(row, mapping)
            if self.accept(model):
                records.append(model)
            else:
                discarded += 1
        warnings = []
        if unknown:
            warnings.append(f"Se ignoraron {len(unknown)} columnas no reconocidas.")
        if discarded:
            warnings.append(
                f"Se descartaron {discarded} filas sin identificadores utilizables."
            )
        warnings.extend(self.report_warnings(records))
        return ImportReport(
            records=records,
            unknown_columns=unknown,
            mapped_columns=mapping,
            rows_read=len(frame),
            rows_accepted=len(records),
            rows_discarded=discarded,
            header_row=header_index + 1,
            warnings=warnings,
        )

    def accept(self, model) -> bool:
        return any(getattr(model, field, None) for field in self.required_any)

    def report_warnings(self, records: list) -> list[str]:
        return []

    def to_model(self, row, mapping):
        raise NotImplementedError
