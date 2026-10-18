"""从NJAV抓取数据"""

import logging
import re

from javsp.datatype import MovieInfo
from javsp.lib import strftime_to_minutes
from javsp.web.base import get_html, get_list_first, select_fc2_cover, xpath_first
from javsp.web.exceptions import CrawlerError, MovieNotFoundError

logger = logging.getLogger(__name__)
base_url = "https://njav.tv/ja"

_SITE = "njav"

# XPath选择器集中定义
XP = {
    "search_list": "//div[@class='box-item']/div[@class='detail']/a",
    "container": "//div[@class='container']/div/div[@class='col']",
    "title": "//div[@class='d-flex justify-content-between align-items-start']/div/h1/text()",
    "thumb": "//div[@id='player']/@data-poster",
    "plot": "//div[@class='description']/p/text()",
    "magnet": "//div[@class='magnet']/a/@href",
    "detail_item": "//div[@class='detail-item']/div",
}


def search_video(movie: MovieInfo):
    id_uc = movie.dvdid
    # 抓取网页
    url = f"{base_url}/search?keyword={id_uc}"
    html = get_html(url)
    list = html.xpath(XP["search_list"])
    video_url = None
    for item in list:
        search_title = item.xpath("text()")[0]
        if id_uc in search_title:
            video_url = item.xpath("@href")
            break
        if id_uc.startswith("FC2-"):
            fc2id = id_uc.replace("FC2-", "")
            if "FC2" in search_title and fc2id in search_title:
                video_url = item.xpath("@href")
                break

    return get_list_first(video_url)


def parse_data(movie: MovieInfo):
    """解析指定番号的影片数据"""
    # 抓取网页
    url = search_video(movie)
    if not url:
        raise MovieNotFoundError(__name__, movie.dvdid)
    html = get_html(url)
    container = xpath_first(html, XP["container"], required=False, label=_SITE)
    if not container:
        raise MovieNotFoundError(__name__, movie.dvdid)

    title = container.xpath(XP["title"])[0]
    thumb_pic = container.xpath(XP["thumb"])
    plot = " ".join(container.xpath(XP["plot"]))
    magnet = container.xpath(XP["magnet"])
    real_id = None
    publish_date = None
    duration_str = None
    serial = None
    producer = None
    genre = []
    actress = []

    for item in container.xpath(XP["detail_item"]):
        item_title = item.xpath("span/text()")[0]
        if "タグ:" in item_title:
            genre += item.xpath("span")[1].xpath("a/text()")
        elif "ジャンル:" in item_title:
            genre += item.xpath("span")[1].xpath("a/text()")
        elif "レーベル:" in item_title:
            genre += item.xpath("span")[1].xpath("a/text()")
        elif "女優:" in item_title:
            actress = item.xpath("span")[1].xpath("a/text()")
        elif "シリーズ:" in item_title:
            serial = get_list_first(item.xpath("span")[1].xpath("a/text()"))
        elif "メーカー:" in item_title:
            producer = get_list_first(item.xpath("span")[1].xpath("a/text()"))
        elif "コード:" in item_title:
            real_id = get_list_first(item.xpath("span")[1].xpath("text()"))
        elif "公開日:" in item_title:
            publish_date = get_list_first(item.xpath("span")[1].xpath("text()"))
        elif "再生時間:" in item_title:
            duration_str = get_list_first(item.xpath("span")[1].xpath("text()"))

    # 清除标题里的番号字符
    keywords = [real_id, " "]
    if movie.dvdid.startswith("FC2"):
        keywords += ["FC2", "PPV", "-"] + [movie.dvdid.split("-")[-1]]
    for keyword in keywords:
        title = re.sub(re.escape(keyword), "", title, flags=re.I)

    # 判断是否无码
    uncensored_arr = magnet + [title]
    movie.uncensored = any("uncensored" in s.lower() for s in uncensored_arr)

    movie.url = url
    movie.title = title
    movie.genre = genre
    movie.actress = actress
    if duration_str:
        movie.duration = str(strftime_to_minutes(duration_str))
    movie.publish_date = publish_date
    movie.producer = producer
    movie.plot = plot
    movie.serial = serial
    movie.magnet = magnet

    # FC2的封面是220x220的，和正常封面尺寸、比例都差太多。如果有预览图片，则使用第一张预览图作为封面
    select_fc2_cover(movie)
    if not movie.cover:
        movie.cover = get_list_first(thumb_pic)


if __name__ == "__main__":

    logger.root.handlers[1].level = logging.DEBUG

    movie = MovieInfo("012023_002")
    try:
        parse_data(movie)
        print(movie)
    except CrawlerError as e:
        logger.error(e, exc_info=True)
