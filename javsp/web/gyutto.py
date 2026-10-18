"""从https://gyutto.com/官网抓取数据"""

import logging
import time

from javsp.datatype import MovieInfo
from javsp.web.base import request_get, resp2html, xpath_first
from javsp.web.exceptions import CrawlerError, MovieNotFoundError

logger = logging.getLogger(__name__)

# https://dl.gyutto.com/i/item266923
base_url = "http://gyutto.com"
base_encode = "euc-jp"

_SITE = "gyutto"

# XPath选择器集中定义
XP = {
    "title": "//h1",
    "img_container": "//a[@class='highslide']/img",
    "info_container": "//dl[@class='BasicInfo clearfix']",
    "plot": "//div[@class='unit_DetailLead']/p/text()",
}


def get_movie_title(html):
    container = xpath_first(html, XP["title"], required=False, label=_SITE)
    if container is None:
        return ""
    return container.text


def get_movie_img(html, index=1):
    images = []
    container = html.xpath(XP["img_container"])
    if len(container) > 0:
        if index == 0:
            return container[0].get("src")

        for row in container:
            images.append(row.get("src"))

    return images


def parse_data(movie: MovieInfo):
    """解析指定番号的影片数据"""
    # 去除番号中的'gyutto'字样
    id_uc = movie.dvdid.upper()
    if not id_uc.startswith("GYUTTO-"):
        raise ValueError("Invalid gyutto number: " + movie.dvdid)
    gyutto_id = id_uc.replace("GYUTTO-", "")
    # 抓取网页
    url = f"{base_url}/i/item{gyutto_id}?select_uaflag=1"
    r = request_get(url, delay_raise=True)
    if r.status_code == 404:
        raise MovieNotFoundError(__name__, movie.dvdid)
    html = resp2html(r, base_encode)
    container = html.xpath(XP["info_container"])

    producer = None
    genre = []
    publish_date = None
    for row in container:
        key = row.xpath(".//dt/text()")
        if not key:
            continue
        if key[0] == "サークル":
            producer = "".join(row.xpath(".//dd/a/text()"))
        elif key[0] == "ジャンル":
            genre = row.xpath(".//dd/a/text()")
        elif key[0] == "配信開始日":
            date = row.xpath(".//dd/text()")
            date_str = "".join(date)
            try:
                date_time = time.strptime(date_str, "%Y年%m月%d日")
                publish_date = time.strftime("%Y-%m-%d", date_time)
            except ValueError:
                logger.debug(f"gyutto日期解析失败: {date_str}")

    plot_tags = html.xpath(XP["plot"])
    plot = plot_tags[0] if plot_tags else None

    movie.title = get_movie_title(html)
    movie.cover = get_movie_img(html, 0)
    movie.preview_pics = get_movie_img(html)
    movie.dvdid = id_uc
    movie.url = url
    movie.producer = producer
    movie.genre = genre if genre else None
    movie.publish_date = publish_date
    movie.plot = plot


if __name__ == "__main__":
    logger.root.handlers[1].level = logging.DEBUG
    movie = MovieInfo("gyutto-266923")

    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=True)
