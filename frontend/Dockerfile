FROM oven/bun:latest

WORKDIR /app

EXPOSE 3000

# Source is bind-mounted at runtime for hot reload.
# bun install runs at startup so the node_modules named volume
# is always populated from the current lockfile.
CMD ["sh", "-c", "bun install && bun run dev"]
