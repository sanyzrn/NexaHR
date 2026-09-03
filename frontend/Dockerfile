# نسخه پین شده و نه برچسبِ شناور: Vite 8 حداقل Node 20.19 می‌خواهد و
# `node:20-alpine` هر شبانه‌روز می‌تواند به هر ۲۰.xای اشاره کند — از جمله
# نسخه‌ای پایین‌تر از آن حداقل. بیلدی که دیروز کار می‌کرد و امروز نه، بدترین
# شکلِ شکستن است.
FROM node:20.19-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# مقادیر پیش‌فرض برای docker-compose محلی؛ روی پلتفرم‌هایی مثل Railway/Render
# با متغیر محیطی سرویس بازنویسی می‌شوند (PORT را خود پلتفرم معمولاً تزریق می‌کند)
ENV PORT=80
ENV BACKEND_ORIGIN=http://backend:8000
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
