import { test, expect } from "@playwright/test";
import { validExactManufacturerUrl } from "../src/integration/exact-manufacturer-url";

test("manufacturer manifest accepts exact numeric ASPX identity, not arbitrary queries", () => {
  for (const url of [
    "https://www.coopar.com.uy/Producto.aspx?id=21",
    "https://manufacturer.invalid/product/one",
    "https://manufacturer.invalid/PRODUCT.ASPX?id=1234567890",
  ]) expect(validExactManufacturerUrl(url), url).toBe(true);
  for (const url of [
    "https://manufacturer.invalid/product?id=21",
    "https://manufacturer.invalid/Producto.aspx?id=0",
    "https://manufacturer.invalid/Producto.aspx?id=01",
    "https://manufacturer.invalid/Producto.aspx?id=21&other=1",
    "https://manufacturer.invalid/Producto.aspx?q=21",
    "https://manufacturer.invalid/Producto.aspx?id=21#part",
    "https://manufacturer.invalid/Producto.aspx?id=%32%31",
    "https://manufacturer.invalid:443/Producto.aspx?id=21",
    "http://manufacturer.invalid/Producto.aspx?id=21",
    "https://user:secret@manufacturer.invalid/Producto.aspx?id=21",
    "https://127.0.0.1/Producto.aspx?id=21",
  ]) expect(validExactManufacturerUrl(url), url).toBe(false);
});
