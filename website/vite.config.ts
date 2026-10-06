import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [
            { name: 'framework', test: /node_modules\/(react|react-dom|scheduler)\// },
            { name: 'motion', test: /node_modules\/(motion|framer-motion|motion-dom|motion-utils)\// },
          ],
        },
      },
    },
  },
});
