const assert = require('node:assert/strict');
const test = require('node:test');
const {receiptFields} = require('../.test-build/receipt-text.cjs');

test('suggests a supplier, readable date and clearly labelled CAD total', () => {
  const text = 'TAX INVOICE\nFictional Food Shop\nSept 21, 2026\nApples 10.20\nSubtotal $1,230.00\nTOTAL\nCAD $1,250.20';
  assert.deepEqual(receiptFields(text), {supplier: 'Fictional Food Shop', date: '2026-09-21', total: '1250.20',
    description: 'Apples', purchaseType: 'Fresh produce'});
});

test('leaves ambiguous dates and totals for the reviewer', () => {
  const text = 'Example Shop\nDate 10/11/26\nTOTAL $18.00\nAMOUNT PAID $12.50';
  assert.deepEqual(receiptFields(text), {supplier: 'Example Shop', date: '', total: '', description: '', purchaseType: ''});
});

test('rejects an invalid date and a total in a different currency', () => {
  const text = 'Example Shop\n2026-02-31\nGrand total USD $8.00';
  assert.deepEqual(receiptFields(text), {supplier: 'Example Shop', date: '', total: '', description: '', purchaseType: ''});
});
