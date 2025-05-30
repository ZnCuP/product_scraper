import logging
import time
import re
from playwright.sync_api import Page, TimeoutError, Error as PlaywrightError

from config import RETRY_ATTEMPTS, RETRY_DELAY_SEC, REQUEST_DELAY_SEC, PLAYWRIGHT_TIMEOUT_MS
from utils import setup_page # 确保导入 setup_page

logger = logging.getLogger(__name__)

def fetch_page_content(page: Page, url: str, attempt: int = 1, is_search_page: bool = False):
    """
    通用函数，用于抓取页面内容，并处理重试逻辑。
    对于搜索页，尝试提取总结果数。
    """
    total_count = None
    try:
        setup_page(page) # 设置页面请求头和图片拦截

        logger.debug(f"请求页面: {url} (尝试 {attempt}/{RETRY_ATTEMPTS})")
        
        # 统一使用 wait_until="domcontentloaded" 确保HTML结构加载完成
        page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS) 
        
        if is_search_page:
            # 搜索页的总结果数通常通过 __NEXT_DATA__ 更可靠，这里作为DOM回退/辅助
            # 简化此处的DOM解析，避免不必要的日志和复杂性
            try:
                # 尝试查找包含总结果数的元素，但不对其可见性做严格等待，只尝试一次
                total_text_element = page.query_selector('div.ItemList_itemTitleWarpper__NZhXV span.ItemList_bold__Anzr9')
                if total_text_element:
                    total_text = total_text_element.inner_text().strip()
                    if total_text.isdigit(): # 检查是否纯数字
                        total_count = int(total_text)
                    else:
                        logger.debug(f"URL {url}: 提取到的总结果文本 '{total_text}' 不是纯数字。")
            except Exception as e:
                logger.debug(f"URL {url}: 尝试从DOM提取总结果数失败: {e}")
        
        # 保持请求延迟，模拟人类行为，避免过快请求
        time.sleep(REQUEST_DELAY_SEC)

        logger.debug(f"成功获取页面: {url}")
        return page.content(), total_count

    except TimeoutError as e:
        logger.warning(f"访问 {url} 时超时 (尝试 {attempt}/{RETRY_ATTEMPTS}): {e}")
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_DELAY_SEC)
            return fetch_page_content(page, url, attempt + 1, is_search_page)
        else:
            logger.error(f"多次尝试后仍无法获取 {url} 的内容。")
            return None, None
    except PlaywrightError as e:
        logger.warning(f"访问 {url} 时 Playwright 错误 (尝试 {attempt}/{RETRY_ATTEMPTS}): {e}")
        if attempt < RETRY_ATTEMPTS:
            time.sleep(RETRY_DELAY_SEC)
            return fetch_page_content(page, url, attempt + 1, is_search_page)
        else:
            logger.error(f"多次尝试后仍无法获取 {url} 的内容。")
            return None, None
    except Exception as e:
        logger.error(f"获取 {url} 时发生未知错误: {e}")
        return None, None