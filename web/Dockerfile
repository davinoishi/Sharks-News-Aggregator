FROM node:20-alpine

WORKDIR /app

COPY package*.json ./

RUN npm install

COPY . .

# Needed at BUILD time, not just runtime. `/about`, `/legal` and `/submit` are
# statically prerendered, so their canonical and og:url are baked into the image
# by `next build` — and a Docker build cannot see the compose `environment:`
# block. Without this the static pages ship canonical="http://localhost:3000/…"
# while the dynamic feed page reports the real origin.
# The compose files pass this through; the default keeps a bare `docker build`
# working for local development.
ARG PUBLIC_SITE_URL=http://localhost:3000
ENV PUBLIC_SITE_URL=$PUBLIC_SITE_URL

RUN npm run build

EXPOSE 3000

CMD ["npm", "start", "--", "-H", "0.0.0.0"]
