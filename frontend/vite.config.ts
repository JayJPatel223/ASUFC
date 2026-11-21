import {readFileSync} from 'node:fs';
import {defineConfig} from 'vite';

const receiptNotices = {
  'tesseract-js.txt': './node_modules/tesseract.js/LICENSE.md',
  'tesseract-core.txt': './node_modules/tesseract.js-core/LICENSE',
  'tesseract-english.txt': './node_modules/@tesseract.js-data/eng/README.md',
};

export default defineConfig(({mode}) => {
  const demo = mode === 'pages';
  return {
    base: demo ? '/ASUFC/' : '/',
    plugins: demo ? [{
      name: 'exclude-desktop-receipt-reader',
      enforce: 'pre',
      resolveId(path) {
        if (path === './receipt-scanner') return '\0desktop-only';
      },
      load(id) {
        if (id === '\0desktop-only') return 'export default function StaffOnly() { return null; }';
      },
    }] : [{
      name: 'receipt-reader-notices',
      apply: 'build',
      generateBundle() {
        for (const [name, path] of Object.entries(receiptNotices)) {
          this.emitFile({type: 'asset', fileName: 'licenses/' + name, source: readFileSync(new URL(path, import.meta.url))});
        }
        const model = new URL('./node_modules/@tesseract.js-data/eng/4.0.0_best_int/eng.traineddata.gz', import.meta.url);
        this.emitFile({
          type: 'asset', fileName: 'assets/receipt-ocr/eng.traineddata.gz', source: readFileSync(model),
        });
      },
    }],
    server: {proxy: demo ? {} : {'/api': {target: 'http://127.0.0.1:8000', rewrite: path => path.replace(/^\/api/, '')}}},
  };
});
