import json
import logging
import re

logger = logging.getLogger(__name__)

def extract_product_info(html_content: str, url: str) -> dict | None:
    """
    从给定的 HTML 内容中提取产品信息。
    优先使用 __NEXT_DATA__ JSON，否则回退到 DOM 解析。
    """
    product_info = {
        'url': url, 'name': '', 'sku': '', 'price': '', 'image_url': '',
        'description': '', 'specifications': {}, 'category': '', 'brand': '',
        'availability': '', 'fitment': '',
        'OE_Number': [],  # 确保这里保留 OE_Number
        'Interchange_Number': [], # 确保这里保留 Interchange_Number
    }

    # 1. 尝试从 __NEXT_DATA__ 提取
    try:
        match = re.search(r'<script id="__NEXT_DATA__" type="application/json">([\s\S]+?)<\/script>', html_content)
        if match:
            json_data = json.loads(match.group(1))
            page_props = json_data.get('props', {}).get('pageProps', {})
            product_data_from_json = page_props.get('detail', {})

            if product_data_from_json:
                product_info['name'] = product_data_from_json.get('title', '')
                product_info['sku'] = product_data_from_json.get('partNumber', '')
                
                discount_price_data = product_data_from_json.get('discountPrice', {})
                original_price_data = product_data_from_json.get('originalPrice', {})
                price_data = discount_price_data if discount_price_data else original_price_data
                if price_data and price_data.get('currency') and price_data.get('cent') is not None:
                    product_info['price'] = f"{price_data['currency']} {price_data['cent'] / (10 ** price_data.get('precision', 2)):.2f}"
                
                images = product_data_from_json.get('itemImages', [])
                if images:
                    # 如果有多张图片，这里只取第一张，或者可以修改为列表
                    product_info['image_url'] = images[0].get('url', '') if images else '' 
                
                # 优先使用SEO描述，其次是descriptionRule
                seo_description = product_data_from_json.get('seo', {}).get('description', '')
                product_info['description'] = seo_description if seo_description else product_data_from_json.get('descriptionRule', '')
                
                product_info['brand'] = product_data_from_json.get('brand', '')
                product_info['availability'] = product_data_from_json.get('usStatus', '')

                # 提取规格和OE/Interchange Number
                for spec_list_key in ['skuCustoms', 'fixedCustoms']:
                    specs_list = product_data_from_json.get(spec_list_key, [])
                    for spec in specs_list:
                        name = (spec.get('label') or spec.get('name') or '').strip()
                        value = (spec.get('value') or '').strip()
                        if name and value:
                            if name.lower() == 'oe number':
                                product_info['OE_Number'].append(value)
                            elif name.lower() == 'interchange number':
                                product_info['Interchange_Number'].append(value)
                            else:
                                product_info['specifications'][name] = value

                # 提取适配信息 (fitment)
                fitment_list = product_data_from_json.get('compatibleData', [])
                if fitment_list:
                    unique_fitment_entries = set()
                    for f in fitment_list:
                        year = f.get('year', '')
                        make = f.get('make', '')
                        model = f.get('model', '')
                        if year and make and model:
                            unique_fitment_entries.add(f"{year} {make} {model}")
                    product_info['fitment'] = "; ".join(sorted(list(unique_fitment_entries)))

                # 清理 None 值
                for key, value in product_info.items():
                    if value is None:
                        product_info[key] = ''
                    elif isinstance(value, list):
                        product_info[key] = [item for item in value if item is not None]

                logger.debug(f"成功从 __NEXT_DATA__ 提取产品信息: {url}")
                return product_info
            else:
                logger.debug(f"URL {url} 的 __NEXT_DATA__ 中未找到 'detail' 字段数据。")
        else:
            logger.debug(f"URL {url} 未找到 __NEXT_DATA__ 脚本。")
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"URL {url} 的 __NEXT_DATA__ 解析或访问失败: {e}")
    except Exception as e:
        logger.warning(f"从 __NEXT_DATA__ 提取产品信息时发生未知错误 ({url}): {e}")

    # 2. 如果 __NEXT_DATA__ 失败或为空，则回退到 DOM 解析
    logger.debug(f"尝试从 DOM 解析产品详情页 (作为备用): {url}")
    
    # 辅助函数：安全地从 re.search 结果中提取并清理文本
    def safe_extract(pattern, text, group=1):
        match = re.search(pattern, text)
        if match:
            return re.sub(r'<[^>]+>', '', match.group(group)).strip()
        return ''

    # 尝试从OG标签或直接DOM元素中提取
    product_info['name'] = product_info['name'] or safe_extract(r'<meta property="og:title" content="([^"]+)"', html_content)
    product_info['name'] = product_info['name'] or safe_extract(r'<h1[^>]*class="[^"]*product-title[^"]*"[^>]*>([\s\S]+?)<\/h1>', html_content)

    product_info['description'] = product_info['description'] or safe_extract(r'<meta property="og:description" content="([^"]+)"', html_content)
    product_info['description'] = product_info['description'] or safe_extract(r'<div[^>]*class="[^"]*ProductDetail_description__[^"]*"[^>]*>([\s\S]+?)<\/div>', html_content)

    product_info['image_url'] = product_info['image_url'] or safe_extract(r'<meta property="og:image" content="([^"]+)"', html_content)
    product_info['image_url'] = product_info['image_url'] or safe_extract(r'<img[^>]*class="[^"]*ProductItem_img__oY1wn[^"]*"[^>]*src="([^"]+)"', html_content)
    
    product_info['price'] = product_info['price'] or safe_extract(r'<span[^>]*class="(?:ProductItem_discountPrice__v4dyL|ProductItem_infoPrice__nrKOL)[^"]*"[^>]*>\s*([\d\.,\s$]+)\s*<\/span>', html_content)

    product_info['sku'] = product_info['sku'] or safe_extract(r'(?:Part\s*#|SKU):\s*<span[^>]*class="[^"]*ProductDetail_value[^"]*"[^>]*>([\s\S]+?)<\/span>', html_content, re.IGNORECASE)
    product_info['sku'] = product_info['sku'] or safe_extract(r'<meta[^>]*itemprop="sku"[^>]*content="([^"]+)"', html_content)

    product_info['brand'] = product_info['brand'] or safe_extract(r'<meta[^>]*itemprop="brand"[^>]*content="([^"]+)"', html_content)
    # 对于品牌，如果 __NEXT_DATA__ 和 meta 都没有，可能需要额外更复杂的 DOM 查找，这里暂不增加，保持精炼

    # 提取 DOM 中的规格和 OE/Interchange Number
    attribute_items_matches = re.finditer(
        r'<li[^>]*class="[^"]*ProductDetail_attributesItem__[^"]*"[^>]*>([\s\S]+?)<\/li>',
        html_content
    )
    for match in attribute_items_matches:
        item_html = match.group(1)
        key_match = re.search(r'<span[^>]*class="[^"]*ProductDetail_attributesKey__[^"]*"[^>]*>([\s\S]+?):<\/span>', item_html)
        val_match = re.search(r'<span[^>]*class="[^"]*ProductDetail_attributesValue__[^"]*"[^>]*>([\s\S]+?)<\/span>', item_html)
        if key_match and val_match:
            key = re.sub(r'<[^>]+>', '', key_match.group(1)).strip()
            val = re.sub(r'<[^>]+>', '', val_match.group(1)).strip()
            if key and val: # 确保键和值都不为空
                if key.lower() == 'oe number':
                    if val not in product_info['OE_Number']:
                        product_info['OE_Number'].append(val)
                elif key.lower() == 'interchange number':
                    if val not in product_info['Interchange_Number']:
                        product_info['Interchange_Number'].append(val)
                else:
                    product_info['specifications'][key] = val

    # 清理 None 值（再次确保，因为DOM解析可能引入None）
    for key, value in product_info.items():
        if value is None:
            product_info[key] = ''
        elif isinstance(value, list):
            product_info[key] = [item for item in value if item is not None]

    # 判断是否成功提取到足够信息
    if product_info['name'] or product_info['description'] or product_info['sku'] or product_info['price'] or product_info['image_url'] or product_info['specifications'] or product_info['fitment'] or product_info['OE_Number'] or product_info['Interchange_Number']:
        logger.debug(f"从 DOM/Meta 提取产品信息完成 (URL: {url})")
        return product_info
    else:
        logger.warning(f"未能从 __NEXT_DATA__ 或 DOM 完整提取产品信息: {url}")
        return None