from dataclasses import dataclass
from io import BytesIO
import pandas as pd
from ...catalog.normalizer import normalize_title

class ExcelImportError(ValueError): pass
@dataclass
class ImportReport:
    records: list
    unknown_columns: list[str]
    mapped_columns: dict[str, str]

class ExcelImporter:
    aliases: dict[str, set[str]] = {}
    required_any: set[str] = set()
    source_label = "archivo"
    def read(self, content: bytes) -> ImportReport:
        try:
            frame = pd.read_excel(BytesIO(content), dtype=object, engine="openpyxl")
        except Exception as exc:
            raise ExcelImportError(f"No se pudo leer el archivo {self.source_label}. Verificá que sea un XLSX válido.") from exc
        mapping: dict[str, str] = {}
        normalized_aliases = {field: {normalize_title(a) for a in names} for field, names in self.aliases.items()}
        for column in frame.columns:
            normalized = normalize_title(column)
            for field, names in normalized_aliases.items():
                if normalized in names and field not in mapping: mapping[field] = str(column)
        if not self.required_any.intersection(mapping):
            expected = ", ".join(sorted(self.required_any))
            raise ExcelImportError(f"No se encontró una columna válida ({expected}) en el archivo de {self.source_label}.")
        known = set(mapping.values())
        return ImportReport([self.to_model(row, mapping) for _, row in frame.iterrows()], [str(c) for c in frame.columns if str(c) not in known], mapping)
    def to_model(self, row, mapping): raise NotImplementedError
