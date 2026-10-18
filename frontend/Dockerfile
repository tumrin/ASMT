FROM node:24-alpine AS build
WORKDIR /app

COPY package.json package-lock.json .npmrc ./
RUN npm ci

COPY . .
RUN npm run build

# The adapter-node output bundles everything (all deps are devDependencies),
# so the runtime stage needs no node_modules.
FROM node:24-alpine
WORKDIR /app

ENV NODE_ENV=production \
    HOST=0.0.0.0 \
    PORT=3000

COPY --from=build /app/build ./build

USER node
EXPOSE 3000
CMD ["node", "build"]
