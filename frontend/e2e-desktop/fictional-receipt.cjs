// The browser generates this fixture in memory using a synthetic receipt.
module.exports = async function insertFictionalReceipt() {
  const canvas = document.createElement('canvas');
  canvas.width = 720;
  canvas.height = 400;
  const context = canvas.getContext('2d');
  context.fillStyle = 'white';
  context.fillRect(0, 0, 720, 400);
  context.fillStyle = 'black';
  context.font = '36px monospace';
  const lines = ['FICTIONAL FOOD SHOP', 'RECEIPT', 'DATE: 2026-11-04', 'SUBTOTAL $10.00', 'TOTAL $12.50'];
  lines.forEach((line, index) => context.fillText(line, 30, 68 + index * 57));
  const image = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
  const ready = new DataTransfer();
  ready.items.add(new File([image], 'fictional-receipt.png', {type: 'image/png'}));
  const input = document.querySelector('input[accept="image/png,image/jpeg"]');
  input.files = ready.files;
  input.dispatchEvent(new Event('change', {bubbles: true}));
};
