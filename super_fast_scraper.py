import os
import json
import logging
from datetime import datetime
from playwright.sync_api import sync_playwright
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "https://a-premium.com"
DATA_DIR = "data"
PRODUCTS_PER_PAGE = 1000
MAX_WORKERS = 8

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scraper.log", encoding="utf-8")
    ]
)

def extract_level3_urls_from_online():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://a-premium.com/categories", wait_until="domcontentloaded", timeout=60000)
        html = page.content()
        browser.close()
    pattern1 = r'"seoUrlHandle"\s*:\s*"([^"]+)"\s*,\s*"level"\s*:\s*3'
    pattern2 = r'"level"\s*:\s*3\s*,\s*"seoUrlHandle"\s*:\s*"([^"]+)"'
    urls = re.findall(pattern1, html) + re.findall(pattern2, html)
    urls = list(set("/" + u for u in urls))
    logging.info(f"共发现{len(urls)}个最底层类型")
    return urls

def parse_products(html):
    m = re.search(
        r'<script[^>]*id=["\']__NEXT_DATA__["\'][^>]*>?([\s\S]+?)</script>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception as e:
        logging.error(f"JSON decode error: {e}")
        return []
    items = data.get("props", {}).get("pageProps", {}).get("filterData", {}).get("itemList", {}).get("data", [])
    products = []
    for p in items:
        url = f"{BASE_URL}/product/{p.get('urlHandle')}" if p.get('urlHandle') else ""
        price = ""
        original_price = ""
        if p.get('discountPrice'):
            price = f"{p['discountPrice'].get('currency','')}" + (f" {p['discountPrice'].get('cent',0)/100:.2f}")
        if p.get('originalPrice'):
            original_price = f"{p['originalPrice'].get('currency','')}" + (f" {p['originalPrice'].get('cent',0)/100:.2f}")
        fitment = ""
        years = p.get("yearValues") or []
        makes = p.get("makeValues") or []
        models = p.get("modelValues") or []
        if years and makes and models:
            fitments = []
            for y in years[:3]:
                for mk in makes[:2]:
                    for md in models[:3]:
                        fitments.append(f"{y} {mk} {md}")
                        if len(fitments) >= 10:
                            break
                    if len(fitments) >= 10:
                        break
                if len(fitments) >= 10:
                    break
            fitment = "; ".join(fitments)
        oe_number = []
        interchange_number = []
        if p.get("skuCustoms"):
            for spec in p["skuCustoms"]:
                name = (spec.get("label") or "").strip().lower()
                value = (spec.get("value") or "").strip()
                if name == "oe number":
                    oe_number.append(value)
                elif name == "interchange number":
                    interchange_number.append(value)
        if p.get("differencesPrompt"):
            dp = p["differencesPrompt"]
            if dp.get("label", "").lower() in ["oe number", "replaces part number"]:
                oe_number += [v.strip() for v in dp.get("value", "").split(",") if v.strip()]
        specifications = {}
        if p.get("skuCustoms"):
            for spec in p["skuCustoms"]:
                name = (spec.get("label") or "").strip()
                value = (spec.get("value") or "").strip()
                if name and value and name.lower() not in ["oe number", "interchange number"]:
                    specifications[name] = value
        for field in ["material", "color", "installation"]:
            if p.get(field):
                specifications[field.capitalize()] = p.get(field)
        products.append({
            "url": url,
            "name": p.get("title", ""),
            "sku": p.get("partNumber", ""),
            "item_number": p.get("itemNumber", ""),
            "bar_code": p.get("barCode", ""),
            "supplier_barcode": p.get("supplierBarcode", ""),
            "seo_title": p.get("seoTitle", ""),
            "sub_title": p.get("subTitle", ""),
            "extra_sub_title": p.get("extraSubTitle", ""),
            "price": price,
            "original_price": original_price,
            "image_url": p.get("imageUrl", ""),
            "category": p.get("frontCategoryTitle", ""),
            "brand": p.get("brand", ""),
            "availability": "In Stock" if p.get("availableTotal", 0) > 0 else "Out of Stock",
            "sales": p.get("sales", 0),
            "review_count": p.get("reviewCount", 0),
            "review_rating": p.get("reviewRating", 0),
            "warranty": p.get("warranty", ""),
            "country": p.get("country", ""),
            "quantity": p.get("quantity", ""),
            "note": p.get("note", ""),
            "fitment": fitment,
            "color": p.get("color", ""),
            "material": p.get("material", ""),
            "installation": p.get("installation", ""),
            "oe_number": oe_number,
            "interchange_number": interchange_number,
            "specifications": specifications,
            "displacements": p.get("displacements", []),
            "year_values": years,
            "make_values": makes,
            "model_values": models,
            "promotion_id": p.get("promotionId", ""),
            "campaign_id": p.get("campaignId", ""),
            "front_category_seo_url": p.get("frontCategorySeoUrl", ""),
            "second_category_seo_url": p.get("secondCategorySeoUrl", "")
        })
    return products

def fetch_category_products(cat_url):
    """
    并发任务：抓取单个分类下所有产品（分页）
    """
    import time
    all_products = []
    url_set = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page_num = 1
        repeat_count = 0
        last_page_data = None
        while True:
            context = browser.new_context()
            page = context.new_page()
            page.route("**/*", lambda route: route.abort() if route.request.resource_type in ["image", "font", "stylesheet", "media"] else route.continue_())
            url = f"{BASE_URL}{cat_url}?page={page_num}&size={PRODUCTS_PER_PAGE}"
            try:
                page.goto(url, wait_until="networkidle", timeout=60000)
                # 增加等待产品列表元素的重试机制
                found = False
                for _ in range(3):
                    try:
                        page.wait_for_selector('.ItemList_collectionContent__aqxzo', timeout=4000)
                        found = True
                        break
                    except Exception:
                        time.sleep(2)
                if not found:
                    logging.warning(f"{cat_url} 多次等待产品列表超时，可能无产品")
                html = page.content()
                products = parse_products(html)
                if last_page_data is not None and products == last_page_data:
                    repeat_count += 1
                    break
                else:
                    repeat_count = 0
                last_page_data = products
                if not products:
                    break
                for prod in products:
                    if prod["url"] and prod["url"] not in url_set:
                        url_set.add(prod["url"])
                        all_products.append(prod)
                if len(products) < PRODUCTS_PER_PAGE:
                    break
            except Exception as e:
                logging.error(f"{cat_url} 第{page_num}页加载失败: {e}")
                break
            finally:
                page.close()
                context.close()
            if not products or repeat_count > 0 or len(products) < PRODUCTS_PER_PAGE:
                break
            page_num += 1
        browser.close()
    return all_products

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = f"{DATA_DIR}/all_products_{timestamp}.json"
    all_products = []
    third_level_urls = extract_level3_urls_from_online()
    logging.info(f"共发现{len(third_level_urls)}个最底层类型")

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_cat = {executor.submit(fetch_category_products, cat_url): cat_url for cat_url in third_level_urls}
        for future in as_completed(future_to_cat):
            cat_url = future_to_cat[future]
            try:
                products = future.result()
                all_products.extend(products)
                logging.info(f"{cat_url} 完成，累计产品数: {len(all_products)}")
            except Exception as exc:
                logging.error(f"{cat_url} 发生异常: {exc}")
            # 实时保存（未去重）
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(all_products, f, ensure_ascii=False, indent=2)

    # 全局去重
    unique = {}
    for prod in all_products:
        key = prod.get("item_number") or prod.get("url")
        if key and key not in unique:
            unique[key] = prod
    unique_products = list(unique.values())
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(unique_products, f, ensure_ascii=False, indent=2)
    logging.info(f"完成！共保存 {len(unique_products)} 条去重后产品到 {out_file}")

if __name__ == "__main__":
    main()