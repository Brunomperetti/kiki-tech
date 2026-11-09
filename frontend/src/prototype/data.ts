export type Status = "Pendiente" | "Conflicto" | "Preparada";
export type Product = {
  id: string;
  sku: string;
  name: string;
  brand: string;
  category: string;
  price: number;
  stock: number;
  status: Status;
  ml: "Verificada" | "SKU coincidente" | "Sin evidencia";
  tn: "Verificada" | "SKU coincidente" | "Sin evidencia";
  color: string;
  initials: string;
};
// Exclusivamente fixtures sintéticos. ID de variante Ecomm, nunca SKU, como identidad.
export const products: Product[] = [
  {
    id: "DEMO-1001",
    sku: "BOT-750",
    name: "Botella térmica · 750 ml",
    brand: "Monte",
    category: "Hogar y tiempo libre",
    price: 28900,
    stock: 42,
    status: "Pendiente",
    ml: "SKU coincidente",
    tn: "Verificada",
    color: "sand",
    initials: "BT",
  },
  {
    id: "DEMO-1002",
    sku: "AUR-BT",
    name: "Auriculares inalámbricos",
    brand: "Nexo",
    category: "Tecnología",
    price: 45900,
    stock: 18,
    status: "Conflicto",
    ml: "SKU coincidente",
    tn: "Sin evidencia",
    color: "violet",
    initials: "AU",
  },
  {
    id: "DEMO-1003",
    sku: "MOC-URB",
    name: "Mochila urbana · verde",
    brand: "Monte",
    category: "Accesorios",
    price: 62900,
    stock: 12,
    status: "Preparada",
    ml: "Verificada",
    tn: "Verificada",
    color: "green",
    initials: "MO",
  },
  {
    id: "DEMO-1004",
    sku: "TAZ-320",
    name: "Taza de cerámica · arena",
    brand: "Casa Sur",
    category: "Hogar y tiempo libre",
    price: 12500,
    stock: 60,
    status: "Pendiente",
    ml: "Sin evidencia",
    tn: "SKU coincidente",
    color: "sand",
    initials: "TZ",
  },
  {
    id: "DEMO-1005",
    sku: "LAMP-01",
    name: "Lámpara de escritorio",
    brand: "Nexo",
    category: "Hogar y tiempo libre",
    price: 38700,
    stock: 9,
    status: "Preparada",
    ml: "Verificada",
    tn: "Sin evidencia",
    color: "violet",
    initials: "LA",
  },
  {
    id: "DEMO-1006",
    sku: "BOT-750",
    name: "Botella térmica · 750 ml coral",
    brand: "Monte",
    category: "Hogar y tiempo libre",
    price: 28900,
    stock: 24,
    status: "Conflicto",
    ml: "SKU coincidente",
    tn: "Sin evidencia",
    color: "coral",
    initials: "BT",
  },
  {
    id: "DEMO-1007",
    sku: "ORG-SET",
    name: "Organizadores · set de 3",
    brand: "Casa Sur",
    category: "Hogar y tiempo libre",
    price: 19800,
    stock: 35,
    status: "Pendiente",
    ml: "Sin evidencia",
    tn: "Verificada",
    color: "green",
    initials: "OR",
  },
  {
    id: "DEMO-1008",
    sku: "PAR-COM",
    name: "Parlante compacto",
    brand: "Nexo",
    category: "Tecnología",
    price: 34900,
    stock: 21,
    status: "Preparada",
    ml: "Verificada",
    tn: "SKU coincidente",
    color: "coral",
    initials: "PA",
  },
];
