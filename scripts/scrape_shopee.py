"""Scrape public Shopee store data into the bot's catalog format.

Only public, SEO-visible data is fetched (no login, no buyer data). Shopee
blocks the product-listing endpoints (search_items/item/get) behind the
`af-ac-enc-dat` anti-bot token unless a real browser generates it, so this
script uses the endpoints that answer plain HTTP requests:

  - shop/get_shop_detail   -> store name, description, rating, location
  - shop/get_categories    -> category list
  - shop/get_shop_seo      -> one product with full tier_variations (color/size)

Usage:
  python scripts/scrape_shopee.py <shop_username> [--out data/shopee.json]

ponytail: only the SEO-visible product is scraped (Shopee exposes exactly one
per shop to crawlers). Full 11-product listing needs a browser console snippet
(see FULL_LIST_SNIPPET) or an af-ac-enc-dat reimplementation; add when a whole
catalog is required.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

import httpx

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "x-api-source": "pc", "accept": "application/json"}
BASE = "https://shopee.co.id/api/v4"

# Price comes as rupiah * 100000 (e.g. 5750000000 == Rp 57.500).
PRICE_DIVISOR = 100000

FULL_LIST_SNIPPET = r"""
// Paste in the browser console on the shop page to grab every product card.
const items = [...document.querySelectorAll('a[href*="-i."]')]
  .map(a => { const m = (a.href||'').match(/i\.(\d+)\.(\d+)/);
    if (!m) return null;
    const name = (a.innerText||'').trim().split('\n')[0];
    const price = (a.querySelector('[class*=price], .\\_1i5HOp, [class*=Price]')?.innerText||'').trim();
    return {itemid: m[1], shopid: m[2], name, price}; })
  .filter(Boolean)
  .filter((v,i,arr) => arr.findIndex(x => x.itemid === v.itemid) === i);
copy(JSON.stringify(items, null, 2));
console.log(items.length + ' items copied to clipboard');
"""


def _api(client: httpx.Client, path: str, params: dict[str, Any]) -> dict:
    resp = client.get(f"{BASE}/{path}", params=params, headers=HEADERS, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def _rupiah(raw: int | None) -> int:
    return int(raw) // PRICE_DIVISOR if raw else 0


def scrape(username: str) -> dict:
    with httpx.Client(follow_redirects=True) as client:
        referer = {"referer": f"https://shopee.co.id/{username}"}
        client.headers.update(referer)

        detail = _api(client, "shop/get_shop_detail", {"username": username})
        shop = detail.get("data") or {}
        shopid = shop.get("shopid")
        if not shopid:
            raise RuntimeError(f"shop not found: {username}")

        cats = _api(client, "shop/get_categories", {"shopid": shopid, "limit": 20, "offset": 0})
        categories = (cats.get("data") or {}).get("shop_categories") or []

        seo = _api(client, "shop/get_shop_seo", {"shopid": shopid})
        seo_items = (seo.get("data") or {}).get("items") or []

    catalog = []
    for it in seo_items:
        name = it.get("name", "").strip()
        price = _rupiah(it.get("price_min")) or _rupiah(it.get("price"))
        sold = it.get("historical_sold") or it.get("sold")
        rating = (it.get("item_rating") or {}).get("rating_star")
        tiers = it.get("tier_variations") or []
        colors = next((t.get("options") or [] for t in tiers if t.get("name") == "Warna"), [])
        sizes = next((t.get("options") or [] for t in tiers if t.get("name") == "Ukuran"), [])

        # One row per color x size variant, matching the bot's "Family - Color - Size X"
        # naming convention so order extraction can pin the right variant.
        if colors and sizes:
            for c in colors:
                for s in sizes:
                    catalog.append({
                        "nama_produk": f"{name} - {c} - Size {s}",
                        "harga": str(price),
                        "ready": "ready" if (it.get("stock") or 0) > 0 else "",
                        "deskripsi": name,
                        "min_order": "1",
                    })
        else:
            catalog.append({
                "nama_produk": name,
                "harga": str(price),
                "ready": "ready" if (it.get("stock") or 0) > 0 else "",
                "deskripsi": name,
                "min_order": "1",
            })

    return {
        "shop": {
            "shopid": shopid,
            "name": shop.get("name"),
            "description": shop.get("description"),
            "location": shop.get("shop_location"),
            "rating": shop.get("rating_star"),
            "followers": shop.get("follower_count"),
            "item_count": shop.get("item_count"),
        },
        "categories": [
            {"id": c.get("shop_category_id"), "name": c.get("display_name"), "total": c.get("total")}
            for c in categories
        ],
        "source": f"https://shopee.co.id/{username}",
        "catalog": catalog,
        "meta": {
            "scraped_products": len(seo_items),
            "total_shop_products": shop.get("item_count"),
            "note": "Only the SEO-visible product is scraped; full listing needs browser console snippet.",
            "sold": sold,
            "rating": rating,
        },
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("username")
    ap.add_argument("--out", default="data/shopee_scrape.json")
    args = ap.parse_args()

    data = scrape(args.username)
    with open(args.out, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {len(data['catalog'])} catalog rows -> {args.out}")
    print(f"shop: {data['shop']['name']} | {data['shop']['item_count']} products total")
    print(f"scraped {data['meta']['scraped_products']} product(s) (SEO-visible only)")
    print()
    print(FULL_LIST_SNIPPET.strip())


if __name__ == "__main__":
    main()
