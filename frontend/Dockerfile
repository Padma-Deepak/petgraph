FROM node:22-alpine

WORKDIR /app

# Install dependencies in a cached layer
COPY package.json package-lock.json* ./
RUN npm ci

# Source is bind-mounted at runtime for HMR.
# This COPY is for non-bind-mount builds only.
COPY . .

EXPOSE 5173

# --host exposes the dev server on all interfaces (required inside Docker).
# VITE_API_TARGET is injected by docker-compose for internal-network proxy routing.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
