FROM oven/bun:latest

WORKDIR /app

# Install deps as a separate layer so they're cached across source-only changes.
COPY package.json bun.lock ./
RUN bun install

COPY . .

EXPOSE 3000

CMD ["bun", "run", "dev"]
