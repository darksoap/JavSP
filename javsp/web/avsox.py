"""从avsox抓取数据"""

import logging

from javsp.config import Cfg, CrawlerID
from javsp.datatype import MovieInfo
from javsp.web.base import get_html, xpath_first
from javsp.web.exceptions import CrawlerError, MovieNotFoundError

logger = logging.getLogger(__name__)
# avsox 的主域名可直接访问，无论是否配代理都用同一主域；此处与 javbus/javdb 保持相同写法，
# 并对缺失的 proxy_free 条目做兜底（注意 base_url 需以 '/' 结尾，下方拼接依赖此）
permanent_url = "https://avsox.click/"
if Cfg().network.proxy_server is not None:
    base_url = permanent_url
else:
    base_url = str(Cfg().network.proxy_free.get(CrawlerID.avsox, permanent_url))

_SITE = "avsox"

# XPath选择器集中定义
XP = {
    "search_id": "//div[@class='photo-info']/span/date[1]/text()",
    "search_url": "//a[contains(@class, 'movie-box')]/@href",
    "container": "/html/body/div[@class='container']",
    "title": "h3/text()",
    "cover": "//a[@class='bigImage']/@href",
    "info": "div/div[@class='col-md-3 info']",
    "dvdid": "p/span[@style]/text()",
    "date": "p/span[text()='发行时间:']",
    "duration": "p/span[text()='长度:']",
    "producer_p": "p[text()='制作商: ']",
    "serial": "p[text()='系列:']",
    "genre": "p/span[@class='genre']/a/text()",
    "actress": "//a[@class='avatar-box']/span/text()",
}


def parse_data(movie: MovieInfo):
    """解析指定番号的影片数据"""
    # avsox无法直接跳转到影片的网页，因此先搜索再从搜索结果中寻找目标网页
    full_id = movie.dvdid
    if full_id.startswith("FC2-"):
        full_id = full_id.replace("FC2-", "FC2-PPV-")
    html = get_html(f"{base_url}tw/search/{full_id}")
    ids = html.xpath(XP["search_id"])
    urls = html.xpath(XP["search_url"])
    ids_lower = list(map(str.lower, ids))
    if full_id.lower() in ids_lower:
        url = urls[ids_lower.index(full_id.lower())]
        url = url.replace("/tw/", "/cn/", 1)
    else:
        raise MovieNotFoundError(__name__, movie.dvdid, ids)

    # 提取影片信息
    html = get_html(url)
    container = xpath_first(html, XP["container"], label=_SITE)
    title = xpath_first(container, XP["title"], label=_SITE)
    cover = xpath_first(container, XP["cover"], label=_SITE)
    info = xpath_first(container, XP["info"], label=_SITE)
    dvdid = xpath_first(info, XP["dvdid"], label=_SITE)
    publish_date = xpath_first(info, XP["date"], label=_SITE).tail.strip()
    duration = xpath_first(info, XP["duration"], label=_SITE).tail.replace("分钟", "").strip()
    producer, serial = None, None
    producer_tag = xpath_first(info, XP["producer_p"], label=_SITE).getnext().xpath("a")
    if producer_tag:
        producer = producer_tag[0].text_content()
    serial_tag = xpath_first(info, XP["serial"], required=False, label=_SITE)
    if serial_tag is not None:
        serial = serial_tag.getnext().xpath("a/text()")[0]
    genre = info.xpath(XP["genre"])
    actress = container.xpath(XP["actress"])

    movie.dvdid = dvdid.replace("FC2-PPV-", "FC2-")
    movie.url = url
    movie.title = title.replace(dvdid, "").strip()
    movie.cover = cover
    movie.publish_date = publish_date
    movie.duration = duration
    movie.genre = genre
    movie.actress = actress
    if full_id.startswith("FC2-"):
        # avsox把FC2作品的拍摄者归类到'系列'而制作商固定为'FC2-PPV'，这既不合理也与其他的站点不兼容，因此进行调整
        movie.producer = serial
    else:
        movie.producer = producer
        movie.serial = serial


if __name__ == "__main__":
    logger.root.handlers[1].level = logging.DEBUG

    movie = MovieInfo("082713-417")
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=True)
