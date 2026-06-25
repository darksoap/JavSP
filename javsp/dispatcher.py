"""爬虫调度：导入爬虫模块、并行抓取"""

import logging
import sys
import threading
import time

import requests
from tqdm import tqdm

try:
    import curl_cffi

    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

from javsp.config import Cfg
from javsp.datatype import GenreMap, Movie, MovieInfo
from javsp.web.exceptions import (
    CredentialError,
    MovieDuplicateError,
    MovieNotFoundError,
    SiteBlocked,
    SitePermissionError,
)

logger = logging.getLogger(__name__)


def import_crawlers():
    """按配置文件的抓取器顺序导入爬虫模块"""
    unknown_mods = []
    for _, mods in Cfg().crawler.selection.items():
        for name in mods:
            try:
                __import__("javsp.web." + name)
            except ModuleNotFoundError:
                unknown_mods.append(name)
    if unknown_mods:
        logger.warning("配置的抓取器无效: " + ", ".join(unknown_mods))


def parallel_crawler(movie: Movie, tqdm_bar=None):
    """使用多线程抓取不同网站的数据"""
    failed_crawlers = []  # (crawler_name, error_reason)

    def wrapper(parser, info: MovieInfo, retry):
        crawler_name = threading.current_thread().name
        short_name = crawler_name.replace("javsp.web.", "")
        for cnt in range(retry):
            try:
                parser(info)
                movie_id = info.dvdid or info.cid
                logger.debug(f"{short_name}: 抓取成功: '{movie_id}': '{info.url}'")
                info._success = True
                if isinstance(tqdm_bar, tqdm) and hasattr(tqdm_bar, "set_description"):
                    tqdm_bar.set_description(f"{short_name}: 抓取完成")
                break
            except MovieNotFoundError as e:
                logger.debug(e)
                failed_crawlers.append((short_name, str(e)))
                break
            except MovieDuplicateError as e:
                logger.debug(str(e))
                failed_crawlers.append((short_name, str(e)))
                break
            except (SiteBlocked, SitePermissionError, CredentialError) as e:
                logger.debug(e)
                failed_crawlers.append((short_name, str(e)))
                break
            except requests.exceptions.RequestException as e:
                logger.debug(f"{short_name}: 网络错误，正在重试 ({cnt + 1}/{retry}): \n{repr(e)}")
                if tqdm_bar is not None and hasattr(tqdm_bar, "set_description"):
                    tqdm_bar.set_description(f"{short_name}: 网络错误，正在重试")
            except Exception as e:
                if CURL_CFFI_AVAILABLE and isinstance(e, curl_cffi.requests.exceptions.RequestException):
                    logger.debug(f"{short_name}: 网络错误，正在重试 ({cnt + 1}/{retry}): \n{repr(e)}")
                    if tqdm_bar is not None and hasattr(tqdm_bar, "set_description"):
                        tqdm_bar.set_description(f"{short_name}: 网络错误，正在重试")
                else:
                    logger.warning(f"{short_name}: 抓取异常: {e}", exc_info=True)
                    failed_crawlers.append((short_name, f"{type(e).__name__}: {e}"))
                    break

    # 根据影片的数据源获取对应的抓取器
    crawler_mods: list[str] = Cfg().crawler.selection[movie.data_src]

    all_info = {i: MovieInfo(movie) for i in crawler_mods}
    # 番号为cid但同时也有有效的dvdid时，也尝试使用普通模式进行抓取
    if movie.data_src == "cid" and movie.dvdid:
        crawler_mods = crawler_mods + Cfg().crawler.selection.normal
        for i in all_info.values():
            i.dvdid = None
        for i in Cfg().crawler.selection.normal:
            all_info[i] = MovieInfo(movie.dvdid)
    thread_pool = []
    for mod_partial, info in all_info.items():
        mod = f"javsp.web.{mod_partial}"
        # 优先使用带数据清洗的 parse_clean_data（如 javdb/javbus 会进行 genre 归一化）
        if hasattr(sys.modules[mod], "parse_clean_data"):
            parser = getattr(sys.modules[mod], "parse_clean_data")
        else:
            parser = getattr(sys.modules[mod], "parse_data")
        # 将all_info中的info实例传递给parser，parser抓取完成后，info实例的值已经完成更新
        th = threading.Thread(target=wrapper, name=mod, args=(parser, info, Cfg().network.retry))
        th.start()
        thread_pool.append(th)
    # 等待所有线程结束
    timeout = Cfg().network.retry * Cfg().network.timeout.total_seconds()
    deadline = time.monotonic() + timeout
    for th in thread_pool:
        th: threading.Thread
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        th.join(timeout=remaining)
    # 根据抓取结果更新影片类型判定
    if movie.data_src == "cid" and movie.dvdid:
        titles = [all_info[i].title for i in Cfg().crawler.selection[movie.data_src]]
        if any(titles):
            movie.dvdid = None
            all_info = {k: v for k, v in all_info.items() if k in Cfg().crawler.selection["cid"]}
        else:
            logger.debug(f"自动更正影片数据源类型: {movie.dvdid} ({movie.cid}): normal")
            movie.data_src = "normal"
            movie.cid = None
            all_info = {k: v for k, v in all_info.items() if k not in Cfg().crawler.selection["cid"]}
    # 删除抓取失败的站点对应的数据
    all_info = {k: v for k, v in all_info.items() if v._success}
    for info in all_info.values():
        info._success = False

    # 智能报错：只有全部失败才汇总输出，单源失败仅记录简要信息
    if not all_info:
        total = len(Cfg().crawler.selection[movie.data_src])
        failed_list = "\n".join(f"  - {name}: {reason}" for name, reason in failed_crawlers)
        movie_id = movie.dvdid or movie.cid or "未知番号"
        raise Exception(f"所有 {total} 个抓取器均失败 ({movie_id}):\n{failed_list}")
    elif failed_crawlers:
        failed_names = {name for name, _ in failed_crawlers}
        logger.info(f"部分抓取器失败: {', '.join(sorted(failed_names))}")  # 抓取失败名单

    # 删除all_info中键名中的'javsp.web.'前缀
    all_info = {k.replace("javsp.web.", ""): v for k, v in all_info.items()}
    # 对各来源的genre进行归一化：优先使用已有的genre_norm，否则根据站点genre_id做映射
    genre_maps = {}
    for name, info in all_info.items():
        if info.genre_norm:
            continue
        if not info.genre_id and not info.genre:
            continue
        try:
            genre_map = genre_maps.setdefault(name, GenreMap(f"data/genre_{name}.csv"))
        except FileNotFoundError:
            logger.debug(f"'{name}' 缺少 genre 映射表，跳过归一化")
            continue
        ids = info.genre_id if info.genre_id else info.genre
        info.genre_norm = genre_map.map(ids)
    return all_info
