export type Status = "Pendiente" | "Conflicto" | "Preparada";
export type Channel = "ml" | "tn";
export type ChannelEvidence = {
  freshness: "current" | "stale" | "unknown";
  publications: { id: string; proof: string; capturedAt: string }[];
};
export type Product = {
  id: string;
  sku: string;
  name: string;
  brand: string;
  category: string;
  presentation: string;
  price: number;
  stock: number;
  status: Status;
  ml: "Verificada" | "SKU coincidente" | "Sin evidencia";
  tn: "Verificada" | "SKU coincidente" | "Sin evidencia";
  color: string;
  initials: string;
  evidence: Record<Channel, ChannelEvidence>;
};
// Fixtures explícitos, solo de dietética. Las publicaciones tienen identidad propia.
export const products: Product[] = [
  {
    id: "DEMO-1001",
    sku: "ALM-NAT",
    name: "Almendras naturales · 250 g",
    brand: "Monte",
    category: "Frutos secos",
    price: 3200,
    stock: 42,
    status: "Pendiente",
    ml: "SKU coincidente",
    tn: "Verificada",
    color: "sand",
    initials: "AL",
    presentation: "250 g",
    evidence: {
      ml: {
        freshness: "current",
        publications: [],
      },
      tn: {
        freshness: "current",
        publications: [
          {
            id: "DEMO-TN-DEMO-1001",
            proof: "Captura sintética TN / DEMO-1001",
            capturedAt: "09/11/2026 12:00",
          },
        ],
      },
    },
  },
  {
    id: "DEMO-1002",
    sku: "NUE-500",
    name: "Nueces mariposa · 500 g",
    brand: "Nexo",
    category: "Frutos secos",
    price: 6900,
    stock: 18,
    status: "Conflicto",
    ml: "SKU coincidente",
    tn: "Sin evidencia",
    color: "violet",
    initials: "NU",
    presentation: "500 g",
    evidence: {
      ml: {
        freshness: "current",
        publications: [],
      },
      tn: {
        freshness: "current",
        publications: [],
      },
    },
  },
  {
    id: "DEMO-1003",
    sku: "CHI-250",
    name: "Semillas de chía · 250 g",
    brand: "Monte",
    category: "Semillas",
    price: 2100,
    stock: 12,
    status: "Preparada",
    ml: "Verificada",
    tn: "Verificada",
    color: "green",
    initials: "CH",
    presentation: "250 g",
    evidence: {
      ml: {
        freshness: "current",
        publications: [
          {
            id: "DEMO-ML-DEMO-1003",
            proof: "Captura sintética ML / DEMO-1003",
            capturedAt: "09/11/2026 12:00",
          },
          {
            id: "DEMO-ML-DEMO-1003",
            proof: "Captura sintética ML / DEMO-1003",
            capturedAt: "09/11/2026 12:00",
          },
          {
            id: "DEMO-ML-SEGUNDA-CHIA",
            proof: "Segunda publicación sintética de la misma variante",
            capturedAt: "09/11/2026 12:00",
          },
        ],
      },
      tn: {
        freshness: "current",
        publications: [
          {
            id: "DEMO-TN-DEMO-1003",
            proof: "Captura sintética TN / DEMO-1003",
            capturedAt: "09/11/2026 12:00",
          },
        ],
      },
    },
  },
  {
    id: "DEMO-1004",
    sku: "HAR-INT",
    name: "Harina integral · 1 kg",
    brand: "Casa Sur",
    category: "Harinas",
    price: 1800,
    stock: 60,
    status: "Preparada",
    ml: "Sin evidencia",
    tn: "SKU coincidente",
    color: "sand",
    initials: "HI",
    presentation: "1 kg",
    evidence: {
      ml: {
        freshness: "current",
        publications: [],
      },
      tn: {
        freshness: "current",
        publications: [],
      },
    },
  },
  {
    id: "DEMO-1005",
    sku: "AVE-500",
    name: "Avena arrollada · 500 g",
    brand: "Nexo",
    category: "Cereales",
    price: 1600,
    stock: 9,
    status: "Preparada",
    ml: "Verificada",
    tn: "Sin evidencia",
    color: "violet",
    initials: "AV",
    presentation: "500 g",
    evidence: {
      ml: {
        freshness: "current",
        publications: [
          {
            id: "DEMO-ML-DEMO-1005",
            proof: "Captura sintética ML / DEMO-1005",
            capturedAt: "09/11/2026 12:00",
          },
        ],
      },
      tn: {
        freshness: "current",
        publications: [],
      },
    },
  },
  {
    id: "DEMO-1006",
    sku: "ALM-NAT",
    name: "Almendras naturales · 1 kg",
    brand: "Monte",
    category: "Frutos secos",
    price: 11000,
    stock: 24,
    status: "Conflicto",
    ml: "SKU coincidente",
    tn: "Sin evidencia",
    color: "coral",
    initials: "AL",
    presentation: "1 kg",
    evidence: {
      ml: {
        freshness: "current",
        publications: [],
      },
      tn: {
        freshness: "unknown",
        publications: [],
      },
    },
  },
  {
    id: "DEMO-1007",
    sku: "LEN-1K",
    name: "Lentejas · 1 kg",
    brand: "Casa Sur",
    category: "Legumbres",
    price: 2400,
    stock: 35,
    status: "Pendiente",
    ml: "Sin evidencia",
    tn: "Verificada",
    color: "green",
    initials: "LE",
    presentation: "1 kg",
    evidence: {
      ml: {
        freshness: "current",
        publications: [],
      },
      tn: {
        freshness: "stale",
        publications: [
          {
            id: "DEMO-TN-DEMO-1007",
            proof: "Captura sintética TN / DEMO-1007",
            capturedAt: "01/10/2026 12:00",
          },
        ],
      },
    },
  },
  {
    id: "DEMO-1008",
    sku: "GAR-500",
    name: "Garbanzos · 500 g",
    brand: "Nexo",
    category: "Legumbres",
    price: 1700,
    stock: 21,
    status: "Preparada",
    ml: "Verificada",
    tn: "SKU coincidente",
    color: "coral",
    initials: "GA",
    presentation: "500 g",
    evidence: {
      ml: {
        freshness: "current",
        publications: [
          {
            id: "DEMO-ML-DEMO-1008",
            proof: "Captura sintética ML / DEMO-1008",
            capturedAt: "09/11/2026 12:00",
          },
        ],
      },
      tn: {
        freshness: "current",
        publications: [],
      },
    },
  },
];
