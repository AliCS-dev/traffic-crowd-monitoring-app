FROM node:26-alpine@sha256:ef24c5053d50fdc3e4e56eb4e7ddb7861874ab0fdc797046ba897581deb8e868 AS build
WORKDIR /app
COPY package.json package-lock.json .nvmrc ./
RUN node -e "if (process.versions.node.split('.')[0] !== require('node:fs').readFileSync('.nvmrc', 'utf8').trim()) throw new Error('Docker Node version must match .nvmrc and CI')" \
    && npm ci
COPY index.html tsconfig*.json vite.config.ts ./
COPY src/ ./src/
ENV VITE_API_BASE_URL=""
RUN npm run build

FROM nginx:stable-alpine@sha256:ef8676b33d681f272ba429b27658bdd7e640963279714c96bddf1dc76307f7b6
COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /app/dist/ /usr/share/nginx/html/
USER 101:101
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD ["wget", "-q", "--spider", "http://127.0.0.1:8080/healthz"]
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
