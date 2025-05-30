import random

# 目标关键词，用于筛选产品
TARGET_KEYWORDS = ["Oil Level Sensor"]

# 默认HTTP请求头，用于Playwright的page.set_extra_http_headers
# 注意：User-Agent会在get_random_user_agent中动态设置
HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'en-US,en;q=0.9',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    'Pragma': 'no-cache',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Upgrade-Insecure-Requests': '1',
}

# 重试机制配置
RETRY_ATTEMPTS = 3  # 网络请求或解析失败时的重试次数
RETRY_DELAY_SEC = 2.5 # 每次重试之间的等待时间（秒）
REQUEST_DELAY_SEC = 2.5 # 每次成功页面请求后的固定延迟（秒），用于模拟人类行为和避免过快请求

# Playwright浏览器配置
PLAYWRIGHT_TIMEOUT_MS = 90000 # Playwright操作的默认超时时间（毫秒）
PLAYWRIGHT_HEADLESS = True # 是否无头模式运行浏览器 (True: 后台运行, False: 显示浏览器窗口)

# 并发进程数配置
MAX_KEYWORD_SCRAPE_WORKERS = 10 # 关键词URL爬取的最大并发进程数
MAX_DETAIL_SCRAPE_WORKERS = 2  # 产品详情爬取的最大并发进程数

# 随机User-Agent列表，用于模拟不同浏览器
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Firefox/125.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Edge/124.0.0.0',
]

def get_random_user_agent():
    """从USER_AGENTS列表中随机选择一个User-Agent。"""
    return random.choice(USER_AGENTS)