"""从JavDB抓取数据"""

import logging
import os
import re

from javsp.avid import guess_av_type
from javsp.chromium import get_browsers_cookies
from javsp.config import Cfg, CrawlerID
from javsp.datatype import GenreMap, MovieInfo
from javsp.web.base import Request, is_cloudflare_challenge, resp2html, xpath_first
from javsp.web.exceptions import (
    CrawlerError,
    CredentialError,
    MovieDuplicateError,
    MovieNotFoundError,
    SiteBlocked,
    SitePermissionError,
    WebsiteError,
)

# 初始化Request实例。使用scraper绕过CloudFlare后，需要指定网页语言，否则可能会返回其他语言网页，影响解析
request = Request(use_scraper=True)
request.headers["Accept-Language"] = "zh-CN,zh;q=0.9,zh-TW;q=0.8,en-US;q=0.7,en;q=0.6,ja;q=0.5"

logger = logging.getLogger(__name__)
genre_map = GenreMap("data/genre_javdb.csv")
permanent_url = "https://javdb.com"
if Cfg().network.proxy_server is not None:
    base_url = permanent_url
else:
    base_url = str(Cfg().network.proxy_free[CrawlerID.javdb])

_SITE = "javdb"

# XPath选择器集中定义
XP = {
    # 搜索结果页
    "search_title": "//div[@class='video-title']/strong/text()",
    "search_url": "//a[@class='box']/@href",
    "search_box": "//a[@class='box']",
    "search_score": "div[@class='score']/span/span",
    "search_meta": "div[@class='meta']/text()",
    # 详情页
    "detail": "/html/body/section/div/div[@class='video-detail']",
    "info_panel": "//nav[@class='panel movie-panel-info']",
    "title": "h2/strong[@class='current-title']/text()",
    "ori_title_link": "//a[contains(@class, 'meta-link') and not(contains(@style, 'display: none'))]",
    "ori_title": "h2/span[@class='origin-title']/text()",
    "cover": "//img[@class='video-cover']/@src",
    "preview_pics": "//a[@class='tile-item'][@data-fancybox='gallery']/@href",
    "preview_video": "//video[@id='preview-video']/source/@src",
    "info_dvdid": "div/span",
    "info_date": "div/strong[text()='日期:']",
    "info_duration": "div/strong[text()='時長:']",
    "info_director": "div/strong[text()='導演:']",
    "info_producer": "div/strong[text()='片商:']",
    "info_seller": "div/strong[text()='賣家:']",
    "info_publisher": "div/strong[text()='發行:']",
    "info_serial": "div/strong[text()='系列:']",
    "info_genre": "//strong[text()='類別:']/../span/a",
    "info_actor": "//strong[text()='演員:']/../span",
    "score_stars": "//span[@class='score-stars']",
    "magnet": "//div[@class='magnet-name column is-four-fifths']/a/@href",
    # CloudFlare检测
    "cf_code": "//span[@class='code-label']/span",
    # 用户信息
    "user_profile": "//div[@class='user-profile']/ul/li[1]/span/following-sibling::text()",
    "user_name": "//div[@class='user-profile']/ul/li[2]/span/following-sibling::text()",
    "user_bio": "//div[@class='p-note user-profile-bio mb-3 js-user-profile-bio']",
}


def get_html_wrapper(url):
    """包装外发的request请求并负责转换为可xpath的html，同时处理Cookies无效等问题"""
    global request, cookies_pool
    r = request.get(url, delay_raise=True)
    if r.status_code == 200:
        # 发生重定向可能仅仅是域名重定向，因此还要检查url以判断是否被跳转到了登录页
        if r.history and "/login" in r.url:
            # 仅在需要时去读取Cookies
            if "cookies_pool" not in globals():
                try:
                    cookies_pool = get_browsers_cookies()
                except (PermissionError, OSError) as e:
                    logger.warning(
                        f"无法从浏览器Cookies文件获取JavDB的登录凭据({e})，可能是安全软件在保护浏览器Cookies文件",
                        exc_info=True,
                    )
                    cookies_pool = []
                except Exception as e:
                    logger.warning(
                        f"获取JavDB的登录凭据时出错({e})，你可能使用的是国内定制版等非官方Chrome系浏览器",
                        exc_info=True,
                    )
                    cookies_pool = []
            if len(cookies_pool) > 0:
                item = cookies_pool.pop()
                request = Request(use_scraper=True)
                request.cookies = item["cookies"]
                if request.scraper:
                    request.scraper.cookies.clear()
                    for k, v in item["cookies"].items():
                        request.scraper.cookies.set(k, v)
                cookies_source = (item["profile"], item["site"])
                logger.debug(f"未携带有效Cookies而发生重定向，尝试更换Cookies为: {cookies_source}")
                return get_html_wrapper(url)
            else:
                raise CredentialError("JavDB: 所有浏览器Cookies均已过期")
        elif r.history and "pay" in r.url.split("/")[-1]:
            raise SitePermissionError(f"JavDB: 此资源被限制为仅VIP可见: '{r.history[0].url}'")
        else:
            html = resp2html(r)
            return html
    elif r.status_code in (403, 503):
        if is_cloudflare_challenge(r):
            # CF挑战页面：无法通过，直接报错
            raise SiteBlocked(f"JavDB: 无法通过CloudFlare检测: {url}")
        # 非CF挑战的403/503：解析站点特定的错误码
        html = resp2html(r)
        code_tag = html.xpath(XP["cf_code"])
        error_code = code_tag[0].text if code_tag else None
        if error_code:
            if error_code == "1020":
                block_msg = f"JavDB: {r.status_code} 禁止访问: 站点屏蔽了来自日本地区的IP地址，请使用其他地区的代理服务器"
            else:
                block_msg = f"JavDB: {r.status_code} 禁止访问: {url} (Error code: {error_code})"
        else:
            block_msg = f"JavDB: {r.status_code} 禁止访问: {url}"
        raise SiteBlocked(block_msg)
    else:
        raise WebsiteError(f"JavDB: {r.status_code} 非预期状态码: {url}")


def get_user_info(site, cookies):
    """获取cookies对应的JavDB用户信息"""
    try:
        request.cookies = cookies
        html = request.get_html(f"https://{site}/users/profile")
    except Exception as e:
        logger.warning("JavDB: 获取用户信息时出错")
        logger.debug(e, exc_info=True)
        return
    # 扫描浏览器得到的Cookies对应的临时域名可能会过期，因此需要先判断域名是否仍然指向JavDB的站点
    if "JavDB" in html.text:
        email = xpath_first(html, XP["user_profile"], label=_SITE)
        username = xpath_first(html, XP["user_name"], label=_SITE)
        return email.strip(), username.strip()
    else:
        logger.debug("JavDB: 域名已过期: " + site)


def get_valid_cookies():
    """扫描浏览器，获取一个可用的Cookies"""
    # 经测试，Cookies所发往的域名不需要和登录时的域名保持一致，只要Cookies有效即可在多个域名间使用
    for d in cookies_pool:
        info = get_user_info(d["site"], d["cookies"])
        if info:
            return d["cookies"]
        else:
            logger.debug(f"{d['profile']}, {d['site']}: Cookies无效")


def parse_data(movie: MovieInfo):
    """从网页抓取并解析指定番号的数据
    Args:
        movie (MovieInfo): 要解析的影片信息，解析后的信息直接更新到此变量内
    """
    # JavDB搜索番号时会有多个搜索结果，从中查找匹配番号的那个
    html = get_html_wrapper(f"{base_url}/search?q={movie.dvdid}")
    ids = list(map(str.lower, html.xpath(XP["search_title"])))
    movie_urls = html.xpath(XP["search_url"])
    match_count = len([i for i in ids if i == movie.dvdid.lower()])
    if match_count == 0:
        raise MovieNotFoundError(__name__, movie.dvdid, ids)
    elif match_count == 1:
        index = ids.index(movie.dvdid.lower())
        new_url = movie_urls[index]
        try:
            html2 = get_html_wrapper(new_url)
        except (SitePermissionError, CredentialError):
            # 不开VIP不让看，过分。决定榨出能获得的信息，毕竟有时候只有这里能找到标题和封面
            box = html.xpath(XP["search_box"])[index]
            movie.url = new_url
            movie.title = box.get("title")
            movie.cover = box.xpath("div/img/@src")[0]
            score_str = xpath_first(box, XP["search_score"], label=_SITE).tail
            score = re.search(r"([\d.]+)分", score_str).group(1)
            movie.score = f"{float(score) * 2:.2f}"
            movie.publish_date = box.xpath(XP["search_meta"])[0].strip()
            return
    else:
        raise MovieDuplicateError(__name__, movie.dvdid, match_count)

    container = xpath_first(html2, XP["detail"], label=_SITE)
    info = xpath_first(container, XP["info_panel"], label=_SITE)
    title = xpath_first(container, XP["title"], label=_SITE)
    show_orig_title = container.xpath(XP["ori_title_link"])
    if show_orig_title:
        movie.ori_title = xpath_first(container, XP["ori_title"], label=_SITE)
    cover = xpath_first(container, XP["cover"], label=_SITE)
    preview_pics = container.xpath(XP["preview_pics"])
    preview_video_tag = container.xpath(XP["preview_video"])
    if preview_video_tag:
        preview_video = preview_video_tag[0]
        if preview_video.startswith("//"):
            preview_video = "https:" + preview_video
        movie.preview_video = preview_video
    dvdid = xpath_first(info, XP["info_dvdid"], label=_SITE).text_content()
    publish_date = xpath_first(info, XP["info_date"], label=_SITE).getnext().text
    duration_tag = xpath_first(info, XP["info_duration"], label=_SITE)
    duration = (
        duration_tag.getnext().text.replace("分鍾", "").strip()
        if duration_tag is not None and duration_tag.getnext() is not None and duration_tag.getnext().text
        else None
    )
    director_tag = xpath_first(info, XP["info_director"], required=False, label=_SITE)
    if director_tag is not None:
        movie.director = director_tag.getnext().text_content().strip()
    av_type = guess_av_type(movie.dvdid)
    if av_type != "fc2":
        producer_tag = xpath_first(info, XP["info_producer"], required=False, label=_SITE)
    else:
        producer_tag = xpath_first(info, XP["info_seller"], required=False, label=_SITE)
    if producer_tag is not None:
        movie.producer = producer_tag.getnext().text_content().strip()
    publisher_tag = xpath_first(info, XP["info_publisher"], required=False, label=_SITE)
    if publisher_tag is not None:
        movie.publisher = publisher_tag.getnext().text_content().strip()
    serial_tag = xpath_first(info, XP["info_serial"], required=False, label=_SITE)
    if serial_tag is not None:
        movie.serial = serial_tag.getnext().text_content().strip()
    score_tag = xpath_first(info, XP["score_stars"], required=False, label=_SITE)
    if score_tag is not None:
        score_str = score_tag.tail or ""
        score_match = re.search(r"([\d.]+)分", score_str)
        if score_match:
            movie.score = f"{float(score_match.group(1)) * 2:.2f}"
    genre_tags = info.xpath(XP["info_genre"])
    genre, genre_id = [], []
    for tag in genre_tags:
        pre_id = tag.get("href").split("/")[-1]
        genre.append(tag.text)
        genre_id.append(pre_id)
        # 判定影片有码/无码
        subsite = pre_id.split("?")[0]
        movie.uncensored = {"uncensored": True, "tags": False}.get(subsite)
    # 新版以 actor-female class 标记女优，旧版在演员链接后使用 ♀ 符号。
    # 逐个检查链接及其紧邻的性别标记，避免缺少标记时名字与性别错位。
    actors_tag = xpath_first(info, XP["info_actor"], label=_SITE)
    actress = []
    for actor in actors_tag.xpath("a"):
        gender = actor.getnext()
        if "actor-female" in actor.get("class", "").split() or (
            gender is not None and gender.tag == "strong" and gender.text_content().strip() == "♀"
        ):
            name = actor.text_content().strip()
            if name:
                actress.append(name)
    magnet = container.xpath(XP["magnet"])

    movie.dvdid = dvdid
    movie.url = new_url.replace(base_url, permanent_url)
    movie.title = title.replace(dvdid, "").strip()
    movie.cover = cover
    movie.preview_pics = preview_pics
    movie.publish_date = publish_date
    movie.duration = duration
    movie.genre = genre
    movie.genre_id = genre_id
    movie.actress = actress
    movie.magnet = [i.replace("[javdb.com]", "") for i in magnet]


def parse_clean_data(movie: MovieInfo):
    """解析指定番号的影片数据并进行清洗"""
    try:
        parse_data(movie)
        # 检查封面URL是否真的存在对应图片
        if movie.cover is not None:
            r = request.head(movie.cover)
            if r.status_code != 200:
                movie.cover = None
    except SiteBlocked:
        logger.error("JavDB: 可能触发了反爬虫机制，请稍后再试")
        raise
    if movie.genre_id and (not movie.genre_id[0].startswith("fc2?")):
        movie.genre_norm = genre_map.map(movie.genre_id)
        movie.genre_id = None  # 没有别的地方需要再用到，清空genre id（表明已经完成转换）


def collect_actress_alias(type=0, use_original=True):
    """
    收集女优的别名
    type: 0-有码, 1-无码, 2-欧美
    use_original: 是否使用原名而非译名，True-田中レモン，False-田中檸檬
    """
    import json
    import random
    import time

    actressAliasMap = {}

    actressAliasFilePath = "data/actress_alias.json"
    # 检查文件是否存在
    if not os.path.exists(actressAliasFilePath):
        # 如果文件不存在，创建文件并写入空字典
        with open(actressAliasFilePath, "w", encoding="utf-8") as file:
            json.dump({}, file)

    typeList = ["censored", "uncensored", "western"]
    page_url = f"{base_url}/actors/{typeList[type]}"
    total_count = 0
    while True:
        try:
            html = get_html_wrapper(page_url)
            actors = html.xpath("//div[@class='box actor-box']/a")

            count = 0
            for actor in actors:
                count += 1
                total_count += 1
                actor.xpath("strong/text()")[0].strip()
                actor_url = actor.xpath("@href")[0]

                # 进入演员主页，获取更多信息
                actor_html = get_html_wrapper(actor_url)
                # 解析演员所有名字信息
                names_span = actor_html.xpath("//span[@class='actor-section-name']")[0]
                aliases_span_list = actor_html.xpath("//span[@class='section-meta']")
                aliases_span = aliases_span_list[0]

                names_list = [name.strip() for name in names_span.text.split(",")]
                if len(aliases_span_list) > 1:
                    aliases_list = [alias.strip() for alias in aliases_span.text.split(",")]
                else:
                    aliases_list = []

                # 将信息添加到actressAliasMap中
                actressAliasMap[names_list[-1 if use_original else 0]] = names_list + aliases_list
                print(f"{total_count} --- {names_list[-1 if use_original else 0]}: {names_list + aliases_list}")

                if count == 10:
                    # 将数据写回文件
                    with open(actressAliasFilePath, encoding="utf-8") as file:
                        existing_data = json.load(file)

                    # 合并现有数据和新爬取的数据
                    existing_data.update(actressAliasMap)

                    # 将合并后的数据写回文件
                    with open(actressAliasFilePath, "w", encoding="utf-8") as file:
                        json.dump(existing_data, file, ensure_ascii=False, indent=2)

                    actressAliasMap = {}  # 重置actressAliasMap

                    print(
                        f"已爬取 {total_count} 个女优，数据已更新并写回文件:",
                        actressAliasFilePath,
                    )

                    # 重置批次计数器
                    count = 0

                time.sleep(max(1, 10 * random.random()))  # 随机等待 1-10 秒

            # 判断是否有下一页按钮
            next_page_link = html.xpath("//a[@rel='next' and @class='pagination-next']/@href")
            if not next_page_link:
                break  # 没有下一页，结束循环
            else:
                next_page_url = f"{next_page_link[0]}"
                page_url = next_page_url

        except SiteBlocked:
            raise

    with open(actressAliasFilePath, encoding="utf-8") as file:
        existing_data = json.load(file)

    # 合并现有数据和新爬取的数据
    existing_data.update(actressAliasMap)

    # 将合并后的数据写回文件
    with open(actressAliasFilePath, "w", encoding="utf-8") as file:
        json.dump(existing_data, file, ensure_ascii=False, indent=2)

    print(f"已爬取 {total_count} 个女优，数据已更新并写回文件:", actressAliasFilePath)


if __name__ == "__main__":
    # collect_actress_alias()
    movie = MovieInfo("FC2-2735981")
    try:
        parse_clean_data(movie)
        print(movie)
    except CrawlerError as e:
        print(repr(e))
