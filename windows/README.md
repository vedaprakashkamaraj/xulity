# xuity — Windows software downloads

A static, searchable single-page site listing free Windows software. Each entry links to the vendor's official download page; no files are hosted here.

## Preview locally

```sh
cd windows
python3 -m http.server 8080
```

Open http://127.0.0.1:8080.

## Deploy

Any static host works: GitHub Pages, Netlify, Vercel, Cloudflare Pages, or a plain nginx/Apache server. For GitHub Pages, point the site to the `windows/` folder (or copy its contents to a `gh-pages` branch).

To add software, edit the `apps` array in `app.js`.
