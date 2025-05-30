import json
import logging
import os
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from playwright.sync_api import sync_playwright

# 导入配置和模块
from config import (
    TARGET_KEYWORDS, MAX_KEYWORD_SCRAPE_WORKERS, MAX_DETAIL_SCRAPE_WORKERS,
    PLAYWRIGHT_HEADLESS, RETRY_ATTEMPTS, RETRY_DELAY_SEC
)
from utils import matches_any_keyword
from fetcher import fetch_page_content
from parser import extract_product_info

# --- 路径和文件名 ---
DATA_DIR = 'data'
LATEST_PRODUCTS_FILENAME = os.path.join(DATA_DIR, 'products_latest.json')
LOG_FILENAME = os.path.join(DATA_DIR, 'scraper.log')

# --- 日志配置 ---
os.makedirs(DATA_DIR, exist_ok=True) # 确保data目录存在
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILENAME, encoding='utf-8', mode='w')
    ]
)
logger = logging.getLogger(__name__)

def scrape_keyword_urls_worker(keyword: str) -> tuple[str, list[str]]:
    """
    工作函数，用于跨多个页面抓取给定关键词的 URL。
    每个工作进程都有自己的浏览器实例。
    """
    logger.info(f"进程开始处理关键词: {keyword}")
    keyword_encoded = keyword.replace(' ', '+')
    all_urls_for_keyword = set()
    initial_page_size = 1000 # 初始页面大小，尝试获取尽可能多的结果

    with sync_playwright() as p:
        browser_instance = p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
        try:
            page = browser_instance.new_page()

            initial_url = f"https://a-premium.com/search?keyword={keyword_encoded}&size={initial_page_size}"
            html_content, total_results = fetch_page_content(page, initial_url, is_search_page=True)
            
            if html_content:
                # 使用 Playwright 定位器提取产品 URL
                product_links_locator = page.locator(
                    'a[href^="/product/"]:not(section.ProductRecommend_container__8_uKx a[href^="/product/"])'
                )
                
                urls_on_page = [
                    f"https://a-premium.com{product_links_locator.nth(i).get_attribute('href')}"
                    for i in range(product_links_locator.count())
                    if product_links_locator.nth(i).get_attribute('href') and product_links_locator.nth(i).get_attribute('href').startswith('/product/')
                ]
                
                all_urls_for_keyword.update(urls_on_page)
                logger.info(f"关键词 '{keyword}' 第一页解析到 {len(urls_on_page)} 条URL。")

                # 如果总结果数已知且需要分页
                if total_results is not None and total_results > len(all_urls_for_keyword): 
                    logger.info(f"关键词 '{keyword}' 共 {total_results} 个结果，需要进一步分页。")
                    # 计算需要爬取的最大页数
                    max_pages_to_scrape = (total_results + initial_page_size - 1) // initial_page_size

                    for page_num_offset in range(1, max_pages_to_scrape): 
                        current_page_num = 1 + page_num_offset
                        page_url = f"https://a-premium.com/search?keyword={keyword_encoded}&page={current_page_num}&size={initial_page_size}"
                        logger.info(f"抓取关键词 '{keyword}' 的第 {current_page_num} 页: {page_url}")
                        
                        html_content_paginated, _ = fetch_page_content(page, page_url, is_search_page=True)
                        if html_content_paginated:
                            product_links_locator_paginated = page.locator(
                                'a[href^="/product/"]:not(section.ProductRecommend_container__8_uKx a[href^="/product/"])'
                            )
                            urls_on_page_paginated = [
                                f"https://a-premium.com{product_links_locator_paginated.nth(i).get_attribute('href')}"
                                for i in range(product_links_locator_paginated.count())
                                if product_links_locator_paginated.nth(i).get_attribute('href') and product_links_locator_paginated.nth(i).get_attribute('href').startswith('/product/')
                            ]
                            
                            if not urls_on_page_paginated and current_page_num > 1:
                                logger.info(f"关键词 '{keyword}' 的第 {current_page_num} 页未找到新的产品URL，停止分页。")
                                break

                            all_urls_for_keyword.update(urls_on_page_paginated)
                            logger.info(f"关键词 '{keyword}' 的第 {current_page_num} 页解析到 {len(urls_on_page_paginated)} 条URL。")
                        else:
                            logger.warning(f"未能获取关键词 '{keyword}' 的第 {current_page_num} 页内容，停止分页。")
                            break 
                else:
                    logger.info(f"关键词 '{keyword}' 仅有 {total_results if total_results is not None else '未知'} 个结果或已完全解析，无需分页。")
            else:
                logger.warning(f"未能获取关键词 '{keyword}' 的第一页内容。")

        except Exception as e:
            logger.error(f"处理关键词 '{keyword}' 时发生错误: {e}")
            traceback.print_exc()
        finally:
            if browser_instance:
                try:
                    browser_instance.close()
                except Exception as e:
                    logger.warning(f"关闭浏览器实例时发生错误: {e}")
                logger.debug(f"进程处理关键词 '{keyword}' 结束，浏览器已关闭。")

    logger.info(f"从搜索关键词 '{keyword}' 最终解析出 {len(all_urls_for_keyword)} 个产品URL。")
    return keyword, list(all_urls_for_keyword)

def scrape_product_detail_worker(url: str) -> tuple[str, dict | None]:
    """
    工作函数，用于抓取单个产品详情页，并实现重试逻辑。
    每个工作进程都有自己的浏览器实例。
    """
    product_data = None 
    
    with sync_playwright() as p:
        browser_instance = None 
        try:
            browser_instance = p.chromium.launch(headless=PLAYWRIGHT_HEADLESS)
            page = browser_instance.new_page()
            
            for attempt in range(RETRY_ATTEMPTS):
                logger.debug(f"尝试获取产品详情: {url} (尝试 {attempt + 1}/{RETRY_ATTEMPTS})")
                html_content, _ = fetch_page_content(page, url, is_search_page=False)

                if html_content:
                    product_data = extract_product_info(html_content, url)
                    if product_data:
                        break # 成功提取到数据，跳出重试循环
                    else:
                        logger.warning(f"未能从 __NEXT_DATA__ 或 DOM 完整提取产品信息: {url} (尝试 {attempt + 1}/{RETRY_ATTEMPTS})")
                else:
                    logger.warning(f"未能获取产品详情页 ({url}) 的内容。") # 这通常意味着 fetch_page_content 已经重试失败

                if attempt < RETRY_ATTEMPTS - 1:
                    time.sleep(RETRY_DELAY_SEC)
            
            if product_data:
                # 构建用于关键词匹配的文本内容
                product_text_content = (
                    f"{product_data.get('name', '')} {product_data.get('description', '')} "
                    f"{product_data.get('sku', '')} {product_data.get('brand', '')} "
                    f"{' '.join(product_data.get('specifications', {}).values())} "
                    f"{product_data.get('fitment', '')} "
                    f"{' '.join(product_data.get('OE_Number', []))} " # 确保 OE_Number 包含在匹配文本中
                    f"{' '.join(product_data.get('Interchange_Number', []))}" # 确保 Interchange_Number 包含在匹配文本中
                )

                if matches_any_keyword(product_text_content, TARGET_KEYWORDS):
                    logger.info(f"产品详情成功爬取并匹配关键词: {url}")
                    return url, product_data
                else:
                    logger.debug(f"产品详情爬取成功但未匹配关键词: {url} (未匹配关键词)")
                    return url, None 
            else:
                logger.warning(f"经过 {RETRY_ATTEMPTS} 次尝试后，仍未能从页面 {url} 提取到有效产品数据。")
                return url, None
        except Exception as e:
            logger.error(f"处理产品详情页 {url} 时发生未知错误: {e}")
            traceback.print_exc()
            return url, None
        finally:
            if browser_instance:
                try:
                    browser_instance.close()
                except Exception as e:
                    logger.warning(f"关闭浏览器实例时发生错误 ({url}): {e}")
                logger.debug(f"进程处理产品详情页 '{url}' 结束，浏览器已关闭。")

def main():
    logger.info("爬虫开始运行...")
    start_time = time.time()

    # --- 1. 加载已存在的 JSON 文件 ---
    existing_products = {}
    if os.path.exists(LATEST_PRODUCTS_FILENAME):
        try:
            with open(LATEST_PRODUCTS_FILENAME, 'r', encoding='utf-8') as f:
                existing_products = json.load(f)
            logger.info(f"已加载 {len(existing_products)} 条现有产品数据。")
        except json.JSONDecodeError as e:
            logger.warning(f"加载现有 JSON 文件失败 ({LATEST_PRODUCTS_FILENAME})，可能是文件损坏或为空: {e}。将从头开始抓取。")
            existing_products = {}
        except Exception as e:
            logger.warning(f"读取现有 JSON 文件时发生未知错误: {e}。将从头开始抓取。")
            existing_products = {}

    existing_urls = set(existing_products.keys())
    logger.info(f"本次运行将跳过已存在于数据文件中的 {len(existing_urls)} 条产品URL。")

    # --- 2. 并行爬取关键词搜索结果URL ---
    all_unique_urls = set()
    logger.info(f"开始并行爬取关键词搜索结果URL... (使用 {MAX_KEYWORD_SCRAPE_WORKERS} 个并发进程)")

    with ProcessPoolExecutor(max_workers=MAX_KEYWORD_SCRAPE_WORKERS) as executor:
        future_to_keyword_urls = {executor.submit(scrape_keyword_urls_worker, keyword): keyword for keyword in TARGET_KEYWORDS}
        for future in as_completed(future_to_keyword_urls):
            keyword = future_to_keyword_urls[future]
            try:
                scraped_keyword, urls_list = future.result()
                if urls_list:
                    all_unique_urls.update(urls_list)
                else:
                    logger.warning(f"关键词 '{scraped_keyword}' 未找到任何URL。")
            except Exception as exc:
                logger.error(f"关键词 '{keyword}' URL 爬取时发生异常: {exc}")
                traceback.print_exc()

    logger.info(f"所有关键词URL爬取完成，共找到 {len(all_unique_urls)} 条唯一产品URL。")

    # --- 3. 过滤掉已存在的 URL 并爬取新的产品详情 ---
    urls_to_scrape_detail = [url for url in all_unique_urls if url not in existing_urls]
    logger.info(f"本次运行需要爬取 {len(urls_to_scrape_detail)} 条新的/未爬取的产品详情。")

    newly_matched_products = {}
    if urls_to_scrape_detail:
        logger.info(f"开始并行爬取 {len(urls_to_scrape_detail)} 条产品详情... (使用 {MAX_DETAIL_SCRAPE_WORKERS} 个并发进程)")
        with ProcessPoolExecutor(max_workers=MAX_DETAIL_SCRAPE_WORKERS) as executor:
            future_to_url_detail = {executor.submit(scrape_product_detail_worker, url): url for url in urls_to_scrape_detail}
            for future in as_completed(future_to_url_detail):
                url = future_to_url_detail[future]
                try:
                    _, product_data = future.result() 
                    if product_data:
                        newly_matched_products[url] = product_data
                except Exception as exc:
                    logger.error(f"产品详情 {url} 爬取时发生异常: {exc}")
                    traceback.print_exc()
        logger.info(f"本次运行新匹配到 {len(newly_matched_products)} 条产品。")
    else:
        logger.info("没有新的产品URL需要爬取详情。")

    # --- 4. 合并新旧数据并保存 ---
    final_products_data = existing_products.copy()
    final_products_data.update(newly_matched_products)

    if final_products_data:
        os.makedirs(DATA_DIR, exist_ok=True)
        try:
            with open(LATEST_PRODUCTS_FILENAME, 'w', encoding='utf-8') as f:
                json.dump(final_products_data, f, ensure_ascii=False, indent=4)
            logger.info(f"所有匹配关键词的产品数据（包括新旧）已保存到 {LATEST_PRODUCTS_FILENAME}。总计 {len(final_products_data)} 条。")
        except Exception as e:
            logger.error(f"保存匹配产品数据到文件 {LATEST_PRODUCTS_FILENAME} 失败: {e}")
    else:
        logger.info("没有匹配关键词的产品数据可以保存。")

    end_time = time.time()
    logger.info(f"爬虫运行结束。总耗时: {end_time - start_time:.2f} 秒。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("用户中断爬虫进程。程序将退出。")
    except Exception as e:
        logger.critical(f"爬虫主程序发生未捕获的错误: {e}")
        traceback.print_exc()