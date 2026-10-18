"""获取各个网站的免代理地址"""

import logging
import re
import sys

from javsp.web.base import get_html, get_resp_text, is_connectable, request_get

logger = logging.getLogger(__name__)


def get_proxy_free_url(site_name: str, prefer_url=None) -> str:
    """获取指定网站的免代理地址
    Args:
        site_name (str): 站点名称
        prefer_url (str, optional): 优先测试此url是否可用
    Returns:
        str: 指定站点的免代理地址（失败时为空字符串）
    """
    if prefer_url and is_connectable(prefer_url, timeout=5):
        return prefer_url
    # 当prefer_url不可用时，尝试自动获取指定网站的免代理地址
    site_name = site_name.lower()
    func_name = f"_get_{site_name}_urls"
    get_funcs = [i for i in dir(sys.modules[__name__]) if i.startswith("_get_")]
    if func_name in get_funcs:
        get_urls = getattr(sys.modules[__name__], func_name)
        try:
            urls = get_urls()
            return _choose_one(urls)
        except Exception:
            return ""
    else:
        raise Exception("Dont't know how to get proxy-free url for " + site_name)


def _choose_one(urls) -> str:
    for url in urls:
        if is_connectable(url, timeout=5):
            return url
    # 全部不可连接时返回第一个作为最佳猜测，避免调用方拿到空字符串
    return urls[0] if urls else ""


def _get_javlib_urls() -> list:
    # 固定的官方/备用域名，作为 bio 解析失败时的兜底
    fallback_urls = ["https://www.javlibrary.com"]
    try:
        html = get_html("https://github.com/javlibcom")
    except Exception:
        logger.debug("获取 javlib GitHub 页面失败，使用备用地址", exc_info=True)
        return fallback_urls
    # GitHub bio 的 class 可能变化，优先用 data-bio-text 属性，回退到 p-note class
    bio_el = html.xpath("//div[@data-bio-text]")
    if not bio_el:
        bio_el = html.xpath("//div[contains(@class, 'p-note')]")
    if not bio_el:
        return fallback_urls
    text = bio_el[0].text_content()
    # bio 格式如 "== c97k ==" 或 "== www.c97k.com =="
    match = re.search(r"([\w][-\w\.]*\w)", text, re.A)
    if match:
        domain = match.group(1)
        # 如果不含点号，视为裸域名，补全为 www.xxx.com
        if "." not in domain:
            domain = f"www.{domain}.com"
        return [f"https://{domain}"]
    return fallback_urls


def _get_javdb_urls() -> list:
    fallback_urls = ["https://javdb.com"]
    try:
        html = get_html("https://jav524.app")
    except Exception:
        logger.debug("获取 javdb 免代理地址失败，使用备用地址", exc_info=True)
        return fallback_urls
    js_links = html.xpath("//script[@src]/@src")
    for link in js_links:
        if "/js/index" in link:
            try:
                text = get_resp_text(request_get(link))
            except Exception:
                continue
            match = re.search(
                r'\$officialUrl\s*=\s*"(https://(?:[\d\w][-\d\w]{1,61}[\d\w]\.){1,2}[a-z]{2,})"',
                text,
                flags=re.I | re.A,
            )
            if match:
                return [match.group(1)]
    return fallback_urls


if __name__ == "__main__":
    print("javdb:\t", _get_javdb_urls())
    print("javlib:\t", _get_javlib_urls())
