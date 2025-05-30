import logging
import re
from playwright.sync_api import Page, Playwright

# 从 config 导入必要的配置
from config import HEADERS, get_random_user_agent, TARGET_KEYWORDS

logger = logging.getLogger(__name__)

def matches_any_keyword(text: str, keywords: list[str]) -> bool:
    """检查给定文本是否包含任何目标关键词（不区分大小写）。"""
    if not text:
        return False
    text_lower = text.lower()
    for keyword in keywords:
        if keyword.lower() in text_lower:
            return True
    return False

def setup_page(page: Page):
    """为 Playwright 页面设置通用配置，如头部和图片拦截。"""
    request_headers = HEADERS.copy()
    request_headers['User-Agent'] = get_random_user_agent()
    page.set_extra_http_headers(request_headers)

    # 阻止加载图片以加速
    page.unroute_all() # 确保之前没有设置的路由被清除
    page.route("**/*", lambda route: route.abort() if route.request.resource_type == "image" else route.continue_())