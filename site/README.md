# xt product site

A static page for https://zitek.cloud/xt/ : `index.html`, `style.css` and `assets/`. No build step,
no JavaScript, no external requests (fonts fall back to the system's). The look follows a dark,
technical style: navy background, light-blue accents, monospace for labels and buttons.

Preview locally: `python3 -m http.server -d site 8000` and open http://127.0.0.1:8000/.

Deploy: `site/deploy.sh` (rsync over the tailnet to orlik, the Hestia web root of zitek.cloud,
into `public_html/xt/`). It needs `ssh orlik` with sudo. The zitek.cloud home page is left alone.

Numbers on the page come from the teams' ledgers and the repo on 28 September 2026; update them
by hand when they change.
