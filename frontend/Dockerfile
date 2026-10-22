# PortfolioIQ frontend image: a static SPA build served by nginx.
#
# VITE_API_BASE_URL is a Vite *build-time* env var -- Vite inlines it into
# the compiled JS, there is no runtime env injection for a plain static
# build like this one. That means it must be passed as a --build-arg at
# image build time, and changing it later requires rebuilding this image,
# not just restarting the container. See docs/DEPLOYMENT.md.

FROM node:20-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
