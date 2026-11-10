"""Authored test products, never downloaded or customer manufacturer documents."""

from io import BytesIO

TEXT = """Nombre: Almendras sintéticas
Marca: Marca sintética KIKI
Fabricante: Fabricante de prueba
EAN: 12345670
Presentación: 250 g
Tipo de venta: Unidad
Ingredientes: Almendras
Alérgenos: Contiene almendras
Energía: 600 kcal/100 g
Proteínas: 20 g/100 g
Contenido neto: 250 g
Declaración comercial: Sin sal agregada
Características: Tostadas
Conservación: Mantener en lugar fresco y seco
Formulación: F-PRUEBA-A
Categoría: Dietética
Subcategoría: Frutos secos
"""


def pdf(
    text=TEXT,
    *,
    active=False,
    empty=False,
    pages=1,
    compressed=False,
    scanned=False,
    encrypted=False,
):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    font_id = writer._add_object(font)
    for _ in range(pages):
        page = writer.add_blank_page(width=595, height=842)
        if scanned:
            from pypdf.generic import NumberObject

            image = DecodedStreamObject()
            image.update(
                {
                    NameObject("/Type"): NameObject("/XObject"),
                    NameObject("/Subtype"): NameObject("/Image"),
                    NameObject("/Width"): NumberObject(1),
                    NameObject("/Height"): NumberObject(1),
                    NameObject("/ColorSpace"): NameObject("/DeviceGray"),
                    NameObject("/BitsPerComponent"): NumberObject(8),
                }
            )
            image.set_data(b"\xff")
            page[NameObject("/Resources")] = DictionaryObject(
                {
                    NameObject("/XObject"): DictionaryObject(
                        {NameObject("/Im1"): writer._add_object(image)}
                    )
                }
            )
            content = DecodedStreamObject()
            content.set_data(b"q 100 0 0 100 10 10 cm /Im1 Do Q")
            page[NameObject("/Contents")] = writer._add_object(content)
        if not empty:
            page[NameObject("/Resources")] = DictionaryObject(
                {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font_id})}
            )
            stream = DecodedStreamObject()
            escaped = [
                line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                for line in text.splitlines()
            ]
            stream.set_data(
                (
                    "BT /F1 10 Tf 30 800 Td 13 TL "
                    + " ".join(f"({line}) Tj T*" for line in escaped)
                    + " ET"
                ).encode("cp1252")
            )
            page[NameObject("/Contents")] = writer._add_object(stream)
            if compressed:
                page.compress_content_streams()
    if active:
        from pypdf.actions import JavaScript

        writer.add_open_action(JavaScript("app.alert('ARCHIVO SINTÉTICO DE PRUEBA');"))
    output = BytesIO()
    if encrypted:
        writer.encrypt("solo-prueba-sintetica", algorithm="AES-256")
    writer.write(output)
    return output.getvalue()
