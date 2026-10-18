"""网络请求的统一接口"""

import contextlib
import logging
import os
import shutil
import sys
import time

import curl_cffi
import lxml.html
import requests
from curl_cffi import requests as curl_requests
from requests.models import Response
from tqdm import tqdm

from javsp.config import Cfg
from javsp.web.exceptions import CrawlerError

__all__ = [
    "Request",
    "get_html",
    "request_get",
    "resp2html",
    "is_cloudflare_challenge",
    "is_connectable",
    "download",
    "get_resp_text",
    "read_proxy",
    "get_list_first",
    "select_fc2_cover",
    "xpath_first",
]


headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"
    )
}

logger = logging.getLogger(__name__)


def is_cloudflare_challenge(resp) -> bool:
    """判断响应是否为CloudFlare挑战/拦截页面

    CloudFlare的反爬是产品级别的，所有站点被拦截时返回的都是同一套标准页面：
    - JS Challenge / Managed Challenge: 403/503 + "Just a moment..." + challenges.cloudflare.com
    - WAF Block: 403 + 错误码(如1020=地区封禁)

    此函数只负责判断"是不是CF挑战页面"，站点特定的错误码解析等逻辑
    由各站点爬虫自行处理。
    """
    if resp.status_code not in (403, 503):
        return False
    try:
        content = resp.content
        # CloudFlare JS Challenge / Managed Challenge 标准页面
        if b"Just a moment" in content:
            return True
        # 旧版CF浏览器验证
        if b"cf-browser-verification" in content:
            return True
        # CF Turnstile/Challenge 脚本
        if b"cf-challenge" in content:
            return True
        if b"challenges.cloudflare.com" in content:
            return True
    except Exception:
        pass
    return False


def read_proxy():
    if Cfg().network.proxy_server is None:
        return {}
    else:
        proxy = str(Cfg().network.proxy_server)
        return {"http": proxy, "https": proxy}


# 与网络请求相关的功能汇总到一个模块中以方便处理，但是不同站点的抓取器又有自己的需求（针对不同网站
# 需要使用不同的UA、语言等）。每次都传递参数很麻烦，而且会面临函数参数越加越多的问题。因此添加这个
# 处理网络请求的类，它带有默认的属性，但是也可以在各个抓取器模块里进行进行定制
class Request:
    """作为网络请求出口并支持各个模块定制功能"""

    def __init__(self, use_scraper=False) -> None:
        # 必须使用copy()，否则各个模块对headers的修改都将会指向本模块中定义的headers变量，导致只有最后一个对headers的修改生效
        self.headers = headers.copy()
        self.cookies = {}

        self.proxies = read_proxy()
        self.timeout = Cfg().network.timeout.total_seconds()
        if not use_scraper:
            self.scraper = None
            self.__get = requests.get
            self.__post = requests.post
            self.__head = requests.head
        else:
            self.scraper = curl_requests.Session(impersonate="chrome")
            self.__get = self._scraper_monitor(self.scraper.get)
            self.__post = self._scraper_monitor(self.scraper.post)
            self.__head = self._scraper_monitor(self.scraper.head)

    def _scraper_monitor(self, func):
        """监控curl_cffi的工作状态，遇到不支持的Challenge时直接抛出异常

        注意：不再回退到requests，因为requests无法绕过CloudFlare TLS指纹检测，
        回退只会导致403而无法真正解决问题。
        """

        def wrapper(*args, **kw):
            try:
                return func(*args, **kw)
            except curl_cffi.CurlError as e:
                logger.debug(f"curl_cffi请求失败: '{e}'")
                raise

        return wrapper

    def get(self, url, cookies=None, timeout=None, delay_raise=False):
        r = self.__get(
            url,
            headers=self.headers,
            proxies=self.proxies,
            cookies=cookies if cookies is not None else self.cookies,
            timeout=timeout if timeout is not None else self.timeout,
        )
        if not delay_raise:
            r.raise_for_status()
        return r

    def post(self, url, data, cookies=None, timeout=None, delay_raise=False):
        r = self.__post(
            url,
            data=data,
            headers=self.headers,
            proxies=self.proxies,
            cookies=cookies if cookies is not None else self.cookies,
            timeout=timeout if timeout is not None else self.timeout,
        )
        if not delay_raise:
            r.raise_for_status()
        return r

    def post_json(self, url, json_data, cookies=None, timeout=None, delay_raise=False):
        """发送 JSON POST 请求"""
        r = self.__post(
            url,
            json=json_data,
            headers=self.headers,
            proxies=self.proxies,
            cookies=cookies if cookies is not None else self.cookies,
            timeout=timeout if timeout is not None else self.timeout,
        )
        if not delay_raise:
            r.raise_for_status()
        return r

    def head(self, url, cookies=None, timeout=None, delay_raise=True):
        r = self.__head(
            url,
            headers=self.headers,
            proxies=self.proxies,
            cookies=cookies if cookies is not None else self.cookies,
            timeout=timeout if timeout is not None else self.timeout,
        )
        if not delay_raise:
            r.raise_for_status()
        return r

    def get_html(self, url):
        r = self.get(url)
        html = resp2html(r)
        return html


class DownloadProgressBar(tqdm):
    def update_to(self, b=1, bsize=1, tsize=None):
        if tsize is not None:
            self.total = tsize
        self.update(b * bsize - self.n)


def request_get(url, cookies=None, timeout=None, delay_raise=False):
    """获取指定url的原始请求"""
    return Request().get(url, cookies=cookies, timeout=timeout, delay_raise=delay_raise)


def get_resp_text(resp: Response, encoding=None):
    """提取Response的文本"""
    if encoding:
        resp.encoding = encoding
    else:
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def get_html(url, encoding="utf-8"):
    """使用get方法访问指定网页并返回经lxml解析后的document"""
    resp = request_get(url)
    text = get_resp_text(resp, encoding=encoding)
    html = lxml.html.fromstring(text)
    html.make_links_absolute(url, resolve_base_href=True)
    # 清理功能仅应在需要的时候用来调试网页（如prestige），否则可能反过来影响调试（如JavBus）
    # html = cleaner.clean_html(html)
    if hasattr(sys, "javsp_debug_mode"):
        lxml.html.open_in_browser(html, encoding=encoding)  # for develop and debug
    return html


def resp2html(resp, encoding="utf-8") -> lxml.html.HtmlElement:
    """将request返回的response转换为经lxml解析后的document"""
    text = get_resp_text(resp, encoding=encoding)
    html = lxml.html.fromstring(text)
    html.make_links_absolute(resp.url, resolve_base_href=True)
    # html = cleaner.clean_html(html)
    if hasattr(sys, "javsp_debug_mode"):
        lxml.html.open_in_browser(html, encoding=encoding)  # for develop and debug
    return html


def get_list_first(lst: list):
    """安全获取列表第一个元素，为空时返回None"""
    return lst[0] if lst else None


def xpath_first(element, path, required=True, label=""):
    """xpath取第一个匹配，失败时给出明确提示

    Args:
        element: lxml元素
        path: XPath表达式
        required: 是否为必需字段，必需字段匹配失败时抛出CrawlerError
        label: 站点标识，用于错误提示

    Returns:
        匹配的第一个元素，无匹配时required=True抛异常，required=False返回None
    """
    result = element.xpath(path)
    if result:
        return result[0]
    if required:
        site = label or "unknown"
        raise CrawlerError(f"XPath匹配失败: [{site}] '{path}' 未找到元素")
    return None


def select_fc2_cover(movie):
    """为FC2影片选择封面：若存在预览图则用第一张预览图替换封面"""
    if movie.preview_pics:
        movie.cover = movie.preview_pics[0]


def is_connectable(url, timeout=3):
    """测试与指定url的连接"""
    try:
        req = Request()
        req.get(url, timeout=timeout)
        return True
    except Exception as e:
        logger.debug(f"Not connectable: {url}\n" + repr(e))
        return False


def urlretrieve(url, filename=None, reporthook=None, extra_headers=None):
    """下载文件，走统一的 Request 出口"""
    req = Request()
    if extra_headers:
        for k, v in extra_headers.items():
            req.headers[k] = v
    with contextlib.closing(req.get(url, timeout=Cfg().network.timeout.total_seconds() * 3)) as r:
        r.raise_for_status()
        header = r.headers
        with open(filename, "wb") as fp:
            bs = 1024
            size = -1
            blocknum = 0
            if "content-length" in header:
                size = int(header["Content-Length"])  # 文件总大小（理论值）
            if reporthook:  # 写入前运行一次回调函数
                reporthook(blocknum, bs, size)
            for chunk in r.iter_content(chunk_size=1024):
                if chunk:
                    fp.write(chunk)
                    fp.flush()
                    blocknum += 1
                    if reporthook:
                        reporthook(blocknum, bs, size)  # 每写入一次运行一次回调函数


def download(url, output_path, desc=None):
    """下载指定url的资源"""
    # 支持“下载”本地资源，以供fc2fan的本地镜像所使用
    if not url.startswith(("http://", "https://")):
        start_time = time.time()
        shutil.copyfile(url, output_path)
        filesize = os.path.getsize(url)
        elapsed = time.time() - start_time
        info = {"total": filesize, "elapsed": elapsed, "rate": filesize / elapsed}
        return info
    if not desc:
        desc = url.split("/")[-1]
    referrer = headers.copy()
    slash_pos = url.find("/", 8)
    referrer["referer"] = url[: slash_pos + 1] if slash_pos != -1 else url + "/"
    with DownloadProgressBar(unit="B", unit_scale=True, miniters=1, desc=desc, leave=False) as t:
        urlretrieve(url, filename=output_path, reporthook=t.update_to, extra_headers=referrer)
        info = {k: t.format_dict[k] for k in ("total", "elapsed", "rate")}
        return info


if __name__ == "__main__":
    download("https://www.javbus.com/pics/cover/6n54_b.jpg", "cover.jpg")
