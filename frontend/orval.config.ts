import { defineConfig } from 'orval'

export default defineConfig({
  apprise: {
    input: {
      target: 'http://localhost:8000/openapi.json',
    },
    output: {
      mode: 'tags-split',
      target: 'src/api/generated',
      schemas: { type: 'zod', path: 'src/api/generated/model' },
      client: 'react-query',
      httpClient: 'axios',
      formatter: 'prettier',
      override: {
        mutator: {
          path: 'src/api/client.ts',
          name: 'customInstance',
        },
        query: {
          useInfinite: false,
          signal: true,
          useInvalidate: true,
          useGetQueryData: true,
          useSetQueryData: true,
        },
      },
    },
    hooks: {
      afterAllFilesWrite: {
        command: 'node scripts/inject-zod-validation.mjs && bunx prettier --write src/api/generated',
        injectGeneratedDirsAndFiles: false,
      },
    },
  },
})
