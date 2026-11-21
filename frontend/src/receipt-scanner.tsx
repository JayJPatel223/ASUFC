import {useEffect, useRef, useState} from 'react';
import {createWorker, OEM} from 'tesseract.js';
import workerPath from 'tesseract.js/dist/worker.min.js?url';
import corePath from 'tesseract.js-core/tesseract-core-lstm.wasm.js?url';
import {receiptFields, ReceiptFields} from './receipt-text';

type Worker = Awaited<ReturnType<typeof createWorker>>;

async function receiptCanvas(file: File) {
  if (!file.size || file.size > 5_000_000 || !['image/jpeg', 'image/png'].includes(file.type)) {
    throw new Error('Choose a JPEG or PNG receipt photo up to 5 MB.');
  }
  const bitmap = await createImageBitmap(file);
  try {
    const canvas = document.createElement('canvas');
    const scale = Math.min(1, 2100 / Math.max(bitmap.width, bitmap.height));
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    const context = canvas.getContext('2d');
    if (!context) throw new Error('Could not prepare this image.');
    context.fillStyle = 'white';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    return canvas;
  } finally {
    bitmap.close();
  }
}

export default function ReceiptScanner({apply}: {apply: (fields: ReceiptFields) => void}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [text, setText] = useState('');
  const [fields, setFields] = useState<ReceiptFields | null>(null);
  const [applied, setApplied] = useState(false);
  const active = useRef(false);
  const worker = useRef<Worker | null>(null);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
      void worker.current?.terminate();
      worker.current = null;
    };
  }, []);

  async function scan() {
    if (!file) return;
    setBusy(true);
    setError('');
    setFields(null);
    setText('');
    setApplied(false);
    let timer: number | undefined;
    let cancelled = false;
    try {
      const image = await receiptCanvas(file);
      const langPath = new URL('/assets/receipt-ocr', window.location.origin).href;
      let workerError: () => void = () => {};
      const failed = new Promise<never>((_resolve, reject) => {
        workerError = () => reject(new Error('Could not read this photo. Try a clearer image.'));
        timer = window.setTimeout(workerError, 35_000);
      });
      const loading = createWorker('eng', OEM.LSTM_ONLY, {
        workerPath, corePath, langPath, workerBlobURL: false, cacheMethod: 'none', errorHandler: workerError,
      }).then(async engine => {
        if (cancelled || !active.current) await engine.terminate();
        else worker.current = engine;
        return engine;
      });
      const engine = await Promise.race([loading, failed]);
      if (!active.current) return;
      const result = await Promise.race([engine.recognize(image), failed]);
      if (active.current) {
        const recognized = result.data.text.trim().slice(0, 5000);
        setText(recognized);
        if (recognized) setFields(receiptFields(recognized));
        else setError('The reader could not find text in this image. Enter the purchase details manually.');
      }
    } catch (failure) {
      if (active.current) setError(failure instanceof Error ? failure.message : 'Could not read this photo. Try a clearer image.');
    } finally {
      cancelled = true;
      window.clearTimeout(timer);
      const engine = worker.current;
      worker.current = null;
      await engine?.terminate();
      if (active.current) setBusy(false);
    }
  }

  return <div>
    <p>Choose a receipt photo to suggest purchase details. The photo stays on this computer.</p>
    <label>Receipt photo<input type="file" accept="image/png,image/jpeg" disabled={busy} onChange={event => {
      setFile(event.target.files?.[0] || null);
      setFields(null);
      setText('');
      setError('');
      setApplied(false);
    }}/></label>
    <button className="secondary" disabled={!file || busy} onClick={scan}>{busy ? 'Reading receipt…' : 'Read receipt photo'}</button>
    {error && <p className="error" role="alert">{error}</p>}
    {fields && <>
      <p>Check the suggested values against the receipt. Leave a field blank to keep the value in the purchase form.</p>
      <label>Suggested supplier<input maxLength={200} value={fields.supplier} onChange={event => setFields({...fields, supplier: event.target.value})}/></label>
      <label>Suggested receipt date<input type="date" value={fields.date} onChange={event => setFields({...fields, date: event.target.value})}/></label>
      <label>Suggested receipt total<input type="number" min=".01" step=".01" value={fields.total} onChange={event => setFields({...fields, total: event.target.value})}/></label>
      <label>Suggested description<input maxLength={1000} value={fields.description} onChange={event => setFields({...fields, description: event.target.value})}/></label>
      <label>Suggested purchase type<input maxLength={100} value={fields.purchaseType} onChange={event => setFields({...fields, purchaseType: event.target.value})}/></label>
      <button className="secondary" disabled={Object.values(fields).every(value => !value.trim())} onClick={() => {
        apply(fields);
        setApplied(true);
      }}>Copy reviewed values to purchase</button>
      {applied && <p role="status">Review the purchase and its allocations before saving.</p>}
      <details><summary>Read text from the photo</summary><pre className="receipt-text">{text}</pre></details>
    </>}
  </div>;
}
