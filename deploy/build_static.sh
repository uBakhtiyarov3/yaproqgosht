#!/usr/bin/env bash
# Mini ilova + admin panel fayllarini shared hostingga (masalan nexiaacademy.uz/yaproqgosht/) tayyorlaydi.
#
#   bash deploy/build_static.sh https://yaproqgosht.duckdns.org
#
# Argument — bot ishlayotgan server manzili (API shu yerda). Natija: dist/yaproqgosht-web.zip
# ZIP ichidagi fayllarni hostingdagi public_html/yaproqgosht/ papkasiga yuklang.
set -euo pipefail
cd "$(dirname "$0")/.."

API="${1:-}"
if [[ ! "$API" =~ ^https:// ]]; then
  echo "Foydalanish: bash deploy/build_static.sh https://SERVER-DOMEN" >&2
  echo "(bot va API ishlayotgan server manzili, https bilan)" >&2
  exit 1
fi
API="${API%/}"
V="$(date +%s)"
OUT="dist/yaproqgosht"
rm -rf dist && mkdir -p "$OUT/admin"

sed "s/{{v}}/$V/g" webapp/index.html > "$OUT/index.html"
cp webapp/app.js webapp/style.css "$OUT/"
sed "s/{{v}}/$V/g" webapp/admin/index.html > "$OUT/admin/index.html"
cp webapp/admin/admin.js webapp/admin/admin.css "$OUT/admin/"
printf 'window.YG_CONFIG = { api: "%s" };\n' "$API" > "$OUT/config.js"

cat > "$OUT/.htaccess" <<'HT'
Options -Indexes
DirectoryIndex index.html
<IfModule mod_headers.c>
  <FilesMatch "\.(html|js|css)$">
    Header set Cache-Control "no-cache"
  </FilesMatch>
  Header always set X-Content-Type-Options "nosniff"
  Header always set Referrer-Policy "no-referrer"
</IfModule>
HT
cat > "$OUT/admin/.htaccess" <<'HT'
<IfModule mod_headers.c>
  Header always set X-Robots-Tag "noindex, nofollow"
</IfModule>
HT

python3 - <<PY
import pathlib, zipfile
root = pathlib.Path("$OUT")
with zipfile.ZipFile("dist/yaproqgosht-web.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(root.rglob("*")):
        if f.is_file():
            z.write(f, f.relative_to(root))
PY
echo "✅ Tayyor: dist/yaproqgosht-web.zip  (API: $API)"
echo "   Hostingda public_html/yaproqgosht/ ga yuklab, Extract qiling."
