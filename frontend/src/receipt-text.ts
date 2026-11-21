export type ReceiptFields = {supplier: string; date: string; total: string; description: string; purchaseType: string};

const months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec'];
const totalLabel = /^(?:grand\s+total|amount\s+(?:paid|due|charged)|total(?:\s+(?:paid|due|cad))?)\b\s*[:=]?\s*/i;
const canadianAmount = /^(?:CAD\s*)?\$?\s*(\d{1,3}(?:,\d{3})*\.\d{2}|\d+\.\d{2})(?:\s*CAD)?$/i;
const paymentLine = /^(subtotal|sub total|total|grand total|amount|hst|gst|tax|visa|debit|credit|mastercard|balance|change|discount|cash|payment)\b/i;
const kinds = {
  'Fresh produce': /\b(apples?|bananas?|berries|carrots?|tomato(?:es)?|potato(?:es)?|avocados?)\b/i,
  'Groceries': /\b(milk|eggs?|bread|rice|pasta|oats|flour|cereal|beans|yogou?rt)\b/i,
  'Hygiene products': /\b(soap|sanitary pads?|toothpaste|toothbrush|shampoo)\b/i,
};

const uniqueValue = (items: string[]) => {
  const values = new Set(items.filter(Boolean));
  return values.size === 1 ? [...values][0] : '';
};

function isoDate(year: string, month: string, day: string) {
  const text = year + '-' + month.padStart(2, '0') + '-' + day.padStart(2, '0');
  const parsed = new Date(text + 'T00:00:00Z');
  return Number.isFinite(parsed.valueOf()) && parsed.toISOString().slice(0, 10) === text ? text : '';
}

export function receiptFields(text: string): ReceiptFields {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
  const supplier = lines.slice(0, 6).find(line => /[a-z]{2}/i.test(line) && !/^\s*(receipt|invoice|tax|date|order|phone|www\.|https?:|total|scan|thanks)\b/i.test(line)) || '';
  const dates: string[] = [];
  const totals: string[] = [];
  const items: string[] = [];
  for (const [index, line] of lines.entries()) {
    for (const match of line.matchAll(/\b(20\d\d)[-/.](\d{1,2})[-/.](\d{1,2})\b/g)) {
      dates.push(isoDate(match[1], match[2], match[3]));
    }
    for (const match of line.matchAll(/\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d\d|\d{2})\b/g)) {
      const year = match[3].length === 2 ? '20' + match[3] : match[3];
      if (Number(match[1]) > 12) dates.push(isoDate(year, match[2], match[1]));
      else if (Number(match[2]) > 12) dates.push(isoDate(year, match[1], match[2]));
    }
    for (const match of line.matchAll(/\b([a-z]{3,9})\.?\s+(\d{1,2}),?\s+(20\d\d)\b/gi)) {
      const month = months.indexOf(match[1].toLowerCase().slice(0, 3)) + 1;
      if (month) dates.push(isoDate(match[3], String(month), match[2]));
    }
    const amount = totalLabel.test(line) && canadianAmount.exec(line.replace(totalLabel, '') || lines[index + 1] || '');
    if (amount && Number(amount[1].replaceAll(',', '')) > 0) totals.push(amount[1].replaceAll(',', ''));
    const item = /^([a-z][^$]{2,60}?)\s+\$?\d+[.]\d{2}$/i.exec(line);
    if (item && !paymentLine.test(item[1])) items.push(item[1].trim());
  }
  const description = [...new Set(items)].slice(0, 4).join(', ');
  const possibleTypes = Object.entries(kinds).filter(([, pattern]) => items.some(item => pattern.test(item))).map(([name]) => name);
  return {supplier: supplier.slice(0, 200), date: uniqueValue(dates), total: uniqueValue(totals), description,
    purchaseType: uniqueValue(possibleTypes)};
}
