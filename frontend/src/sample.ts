// SAMPLE FIGURES for the dashboard layout. Every widget reads from here until
// it is connected to the API; the page shows a "Sample data" label while any
// of this is in use. Nothing here comes from a real business.

export type OrderStatus = 'delivered' | 'processing' | 'shipped' | 'cancelled'

export const sample = {
  recentOrders: {
    value: 18745,
    change: -8.4,
    lastMonth: 20461,
    points: [
      { label: '1', value: 1200 }, { label: '4', value: 1650 }, { label: '8', value: 1500 },
      { label: '11', value: 1280 }, { label: '15', value: 1580 }, { label: '18', value: 1820 },
      { label: '22', value: 1610 }, { label: '25', value: 1540 }, { label: '29', value: 2104 },
      { label: '31', value: 2380 },
    ],
    highlight: 8,
  },
  customers: {
    current: 2847,
    currentChange: 12.6,
    fresh: 742,
    freshChange: 16.3,
    split: [
      { label: 'Shop 1', percent: 58, value: 1652, change: 9.8 },
      { label: 'Shop 2', percent: 42, value: 1195, change: 15.7 },
    ],
  },
  revenue: {
    value: 124680,
    change: 22.7,
    lastMonth: 101630,
    // this week / last week, Monday to Sunday
    week: [
      [9800, 6200], [18500, 3800], [14900, 4600], [21200, 3200], [29800, 2900], [24600, 3400], [19900, 2600],
    ] as [number, number][],
  },
  categories: [
    { name: 'Paper', percent: 30 },
    { name: 'Pens', percent: 22 },
    { name: 'Notebooks', percent: 18 },
    { name: 'Files', percent: 15 },
    { name: 'Art supplies', percent: 10 },
    { name: 'Other', percent: 5 },
  ],
  // income and profit per day
  orders: [
    [5600, 900], [4800, 800], [6100, 1300], [5300, 900], [4700, 800], [4600, 900], [4620, 1080],
    [4200, 900], [3900, 800], [4600, 800], [5300, 900], [6300, 1400], [5900, 1300], [4900, 900], [4600, 900],
  ] as [number, number][],
  hours: [
    { label: '08–10', percent: 24 },
    { label: '10–12', percent: 29 },
    { label: '12–15', percent: 21 },
    { label: '15–18', percent: 16 },
    { label: '18+', percent: 10 },
  ],
  products: [
    { name: 'A4 paper ream', stock: 156, oldPrice: 49.99, sale: 15, sold: 320 },
    { name: 'Spiral notebook', stock: 98, oldPrice: 19.99, sale: 20, sold: 210 },
    { name: 'Ballpoint pens, box of 50', stock: 214, oldPrice: 59.99, sale: 10, sold: 178 },
    { name: 'Lever arch file', stock: 67, oldPrice: 29.99, sale: 25, sold: 96 },
    { name: 'Coloured pencils, 24', stock: 132, oldPrice: 39.99, sale: 12, sold: 142 },
  ],
  recent: [
    { id: 'ORD-7956', customer: 'Customer A', amount: 149.99, status: 'delivered' as OrderStatus, hoursAgo: 2 },
    { id: 'ORD-7955', customer: 'Customer B', amount: 89.5, status: 'processing' as OrderStatus, hoursAgo: 4 },
    { id: 'ORD-7954', customer: 'Customer C', amount: 199, status: 'shipped' as OrderStatus, hoursAgo: 6 },
    { id: 'ORD-7953', customer: 'Customer D', amount: 59.49, status: 'processing' as OrderStatus, hoursAgo: 8 },
    { id: 'ORD-7952', customer: 'Customer E', amount: 249, status: 'cancelled' as OrderStatus, hoursAgo: 10 },
  ],
}
