"""从FC2PPVDB抓取数据"""

import logging

from javsp.datatype import MovieInfo
from javsp.lib import strftime_to_minutes
from javsp.web.base import get_html, get_list_first, select_fc2_cover, xpath_first
from javsp.web.exceptions import CrawlerError, MovieNotFoundError

logger = logging.getLogger(__name__)
base_url = "https://fc2ppvdb.com"

_SITE = "fc2ppvdb"

# XPath选择器集中定义
XP = {
    "container": "//div[@class='container lg:px-5 px-2 py-12 mx-auto']/div[1]",
    "title": "//h2/a/text()",
    "duration": "//div[starts-with(text(),'収録時間：')]/span/text()",
    "actress": "//div[starts-with(text(),'女優：')]/span/a/text()",
    "genre": "//div[starts-with(text(),'タグ：')]/span/a/text()",
    "date": "//div[starts-with(text(),'販売日：')]/span/text()",
    "publisher": "//div[starts-with(text(),'販売者：')]/span/a/text()",
    "mosaic": "//div[starts-with(text(),'モザイク：')]/span/text()",
    "preview_video": "//a[starts-with(text(),'サンプル動画')]/@href",
}


def parse_data(movie: MovieInfo):
    """解析指定番号的影片数据"""
    # 去除番号中的'FC2'字样
    id_uc = movie.dvdid.upper()
    if not id_uc.startswith("FC2-"):
        raise ValueError("Invalid FC2 number: " + movie.dvdid)
    fc2_id = id_uc.replace("FC2-", "")
    # 抓取网页
    url = f"{base_url}/articles/{fc2_id}"
    html = get_html(url)
    container = xpath_first(html, XP["container"], required=False, label=_SITE)
    if not container:
        raise MovieNotFoundError(__name__, movie.dvdid)

    title = container.xpath(XP["title"])
    thumb_pic = container.xpath(f"//img[@alt='{fc2_id}']/@src")
    duration_str = container.xpath(XP["duration"])
    actress = container.xpath(XP["actress"])
    genre = container.xpath(XP["genre"])
    publish_date = container.xpath(XP["date"])
    publisher = container.xpath(XP["publisher"])
    uncensored_str = container.xpath(XP["mosaic"])
    uncensored_str_f = get_list_first(uncensored_str)
    uncensored = True if uncensored_str_f == "無" else False if uncensored_str_f == "有" else None
    preview_video = container.xpath(XP["preview_video"])

    movie.dvdid = id_uc
    movie.url = url
    movie.title = get_list_first(title)
    movie.genre = genre
    movie.actress = actress
    duration_val = get_list_first(duration_str)
    if duration_val:
        movie.duration = str(strftime_to_minutes(duration_val))
    movie.publish_date = get_list_first(publish_date)
    movie.publisher = get_list_first(publisher)
    movie.uncensored = uncensored
    movie.preview_video = get_list_first(preview_video)

    # FC2的封面是220x220的，和正常封面尺寸、比例都差太多。如果有预览图片，则使用第一张预览图作为封面
    select_fc2_cover(movie)
    if not movie.cover:
        movie.cover = get_list_first(thumb_pic)


if __name__ == "__main__":
    logger.root.handlers[1].level = logging.DEBUG

    movie = MovieInfo("FC2-4497837")
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=True)
