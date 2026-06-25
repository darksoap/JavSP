"""定义数据类型和一些通用性的对数据类型的操作"""

import csv
import json
import logging
import os
import re
import shutil
from functools import cached_property

from pydantic import BaseModel, ConfigDict, PrivateAttr, model_validator

from javsp.avid import get_id, normalize_id
from javsp.config import Cfg
from javsp.lib import detect_special_attr, resource_path

logger = logging.getLogger(__name__)
filemove_logger = logging.getLogger("filemove")


def setup_filemove_log(cfg, log_dir=None):
    """配置 filemove_logger 的 FileHandler，将文件移动详情写入 filemove.log

    Args:
        cfg: 配置对象
        log_dir: 日志文件存放目录，为 None 时使用当前工作目录
    """
    if not cfg.summarizer.filemove_log:
        return
    if any(isinstance(h, logging.FileHandler) for h in filemove_logger.handlers):
        return
    log_path = "filemove.log" if log_dir is None else os.path.join(log_dir, "filemove.log")
    filemove_handler = logging.FileHandler(log_path, encoding="utf-8")
    filemove_handler.setLevel(logging.DEBUG)
    filemove_handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    filemove_logger.addHandler(filemove_handler)
    filemove_logger.setLevel(logging.DEBUG)


class MovieInfo(BaseModel):
    """影片元数据信息

    支持三种构造方式:
      MovieInfo("ABC-123")       - 通过 dvdid 构造
      MovieInfo(cid="abc00123")  - 通过 cid 构造
      MovieInfo(from_file="...") - 从 JSON 文件加载
    也支持从 Movie 实例构造: MovieInfo(movie)
    """

    model_config = ConfigDict(populate_by_name=True)

    # 标识字段（构造时必须提供其中之一）
    dvdid: str | None = None  # DVD ID，即通常的番号
    cid: str | None = None  # DMM Content ID

    # 影片元数据字段
    url: str | None = None  # 影片页面的URL
    plot: str | None = None  # 故事情节
    ori_plot: str | None = None  # 原始故事情节，仅在简介被翻译过时才对此字段赋值
    cover: str | None = None  # 封面图片（URL）
    big_cover: str | None = None  # 高清封面图片（URL）
    genre: list[str] | None = None  # 影片分类的标签
    genre_id: list[str] | None = None  # 影片分类的标签的ID
    genre_norm: list[str] | None = None  # 统一后的影片分类的标签
    score: float | None = None  # 评分（10分制，两位浮点数）
    title: str | None = None  # 影片标题（不含番号）
    ori_title: str | None = None  # 原始影片标题，仅在标题被处理过时才对此字段赋值
    magnet: list[str] | None = None  # 磁力链接
    serial: str | None = None  # 系列
    actress: list[str] | None = None  # 出演女优
    actress_pics: dict[str, str] | None = None  # 出演女优的头像
    director: str | None = None  # 导演
    duration: str | None = None  # 影片时长
    producer: str | None = None  # 制作商
    publisher: str | None = None  # 发行商
    uncensored: bool | None = None  # 是否为无码影片
    publish_date: str | None = None  # 发布日期
    preview_pics: list[str] | None = None  # 预览图片（URL）
    preview_video: str | None = None  # 预览视频（URL）

    # 动态属性（由汇总/命名逻辑设置，不参与序列化）
    nfo_title: str | None = None
    label: str | None = None
    covers: list[str] | None = None
    big_covers: list[str] | None = None
    title_break: list[str] | None = None
    ori_title_break: list[str] | None = None
    field_sources: dict[str, str] | None = None  # 字段级数据来源追踪，如 {"title": "javbus", "actress": "javdb"}

    # 私有属性（不参与序列化和 model_fields）
    _success: bool = PrivateAttr(default=False)

    @model_validator(mode="before")
    @classmethod
    def _coerce_movie_input(cls, data):
        """支持从 Movie 实例或位置参数构造"""
        if isinstance(data, dict):
            # 处理 from_file 参数
            from_file = data.pop("from_file", None)
            if from_file is not None:
                if not isinstance(from_file, str):
                    raise TypeError(f"from_file must be a string path, got {type(from_file)}")
                if not os.path.isfile(from_file):
                    raise TypeError(f"Invalid file path: '{from_file}'")
                with open(from_file, encoding="utf-8") as f:
                    file_data = json.load(f)
                # 合并已有的键
                for k, v in file_data.items():
                    if k not in data or data[k] is None:
                        data[k] = v
            return data
        # 如果传入的是 Movie 实例或其他对象
        if hasattr(data, "dvdid") and hasattr(data, "cid"):
            return {"dvdid": data.dvdid, "cid": data.cid}
        return data

    def __init__(self, dvdid: str = None, /, *, cid: str = None, from_file=None, **kwargs):
        """兼容旧式构造方式

        MovieInfo("ABC-123")       -> dvdid="ABC-123"
        MovieInfo(cid="abc00123")  -> cid="abc00123"
        MovieInfo(from_file="...") -> 从文件加载
        MovieInfo(movie)           -> 从 Movie 实例提取 dvdid/cid
        """
        # 处理位置参数：如果 dvdid 是 Movie 实例
        if isinstance(dvdid, Movie):
            kwargs.setdefault("dvdid", dvdid.dvdid)
            kwargs.setdefault("cid", dvdid.cid)
            super().__init__(**kwargs)
            return

        if dvdid is not None:
            kwargs.setdefault("dvdid", dvdid)
        if cid is not None:
            kwargs.setdefault("cid", cid)
        if from_file is not None:
            kwargs["from_file"] = from_file

        # 校验：必须提供 dvdid/cid/from_file 之一
        has_id = kwargs.get("dvdid") or kwargs.get("cid") or kwargs.get("from_file")
        if not has_id and not kwargs.get("title"):  # 允许从文件加载时暂无 id
            # 宽松模式：from_file 在 model_validator 中处理，这里不做严格校验
            pass

        super().__init__(**kwargs)

    def __repr__(self) -> str:
        if self.dvdid:
            expression = f"('{self.dvdid}')"
        else:
            expression = f"('cid={self.cid}')"
        return self.__class__.__name__ + expression

    def dump(self, filepath=None, crawler=None) -> None:
        """将影片信息序列化到 JSON 文件"""
        if not filepath:
            id = self.dvdid if self.dvdid else self.cid
            if crawler:
                filepath = f"../unittest/data/{id} ({crawler}).json"
                filepath = os.path.join(os.path.dirname(__file__), filepath)
            else:
                filepath = id + ".json"
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    def load(self, filepath) -> None:
        """从 JSON 文件加载数据并更新当前实例（已弃用，建议直接使用 MovieInfo(from_file=...)）"""
        with open(filepath, encoding="utf-8") as f:
            d = json.load(f)
        # 只更新模型中已定义的字段
        for k, v in d.items():
            if k in self.model_fields:
                setattr(self, k, v)

    def get_info_dic(self) -> dict[str, str]:
        """生成用来填充模板的字典"""
        info = self
        d = {}
        d["num"] = info.dvdid or info.cid
        d["title"] = info.title or Cfg().summarizer.default.title
        d["rawtitle"] = info.ori_title or d["title"]
        d["actress"] = ",".join(info.actress) if info.actress else Cfg().summarizer.default.actress
        d["score"] = info.score or "0"
        d["censor"] = Cfg().summarizer.censor_options_representation[1 if info.uncensored else 0]
        d["serial"] = info.serial or Cfg().summarizer.default.series
        d["director"] = info.director or Cfg().summarizer.default.director
        d["producer"] = info.producer or Cfg().summarizer.default.producer
        d["publisher"] = info.publisher or Cfg().summarizer.default.publisher
        d["date"] = info.publish_date or "0000-00-00"
        d["year"] = d["date"].split("-")[0]
        # cid中不会出现'-'，可以直接从d['num']拆分出label
        num_items = d["num"].split("-")
        d["label"] = num_items[0] if len(num_items) > 1 else "---"
        d["genre"] = ",".join(info.genre_norm if info.genre_norm else info.genre if info.genre else [])

        return d

    @classmethod
    def get_merge_fields(cls) -> list[str]:
        """返回参与数据汇总合并的字段名列表（替代 dir() 反射）"""
        return [name for name in cls.model_fields if name not in ("dvdid", "cid")]


class Movie:
    """用于关联影片文件的类"""

    def __init__(self, dvdid=None, /, *, cid=None) -> None:
        arg_count = len([i for i in (dvdid, cid) if i])
        if arg_count != 1:
            raise TypeError(f"Require 1 parameter but {arg_count} given")
        # 创建类的默认属性
        self.dvdid = dvdid  # DVD ID，即通常的番号
        self.cid = cid  # DMM Content ID
        self.files = []  # 关联到此番号的所有影片文件的列表（用于管理带有多个分片的影片）
        self.data_src = "normal"  # 数据源：不同的数据源将使用不同的爬虫
        self.info: MovieInfo = None  # 抓取到的影片信息
        self.save_dir = None  # 存放影片、封面、NFO的文件夹路径
        self.basename = None  # 按照命名模板生成的不包含路径和扩展名的basename
        self.nfo_file = None  # nfo文件的路径
        self.fanart_file = None  # fanart文件的路径
        self.poster_file = None  # poster文件的路径
        self.guid = None  # GUI使用的唯一标识，通过dvdid和files做md5生成

    @cached_property
    def hard_sub(self) -> bool:
        """影片文件带有内嵌字幕"""
        return "C" in self.attr_str

    @cached_property
    def uncensored(self) -> bool:
        """影片文件是无码流出/无码破解版本（很多种子并不严格区分这两种，故这里也不进一步细分）"""
        return "U" in self.attr_str

    @cached_property
    def attr_str(self) -> str:
        """用来标示影片文件的额外属性的字符串(空字符串/-U/-C/-UC)"""
        # 暂不支持多分片的影片
        if len(self.files) != 1:
            return ""
        r = detect_special_attr(self.files[0], self.dvdid)
        if r:
            r = "-" + r
        return r

    def __repr__(self) -> str:
        if self.cid and self.data_src == "cid":
            expression = f"('cid={self.cid}')"
        else:
            expression = f"('{self.dvdid}')"
        return __class__.__name__ + expression

    def rename_files(self, use_hardlink: bool = False) -> list:
        """根据命名规则移动（重命名）影片文件

        Args:
            use_hardlink: 为 True 时创建硬链接而非移动源文件（源文件保留）。

        Returns:
            list[(src, dst)]: 所有已移动文件的(原路径, 新路径)列表
        """

        def move_file(src: str, dst: str):
            """移动（重命名）文件并记录信息到日志

            影片文件目标已存在时抛 FileExistsError 以中断流程（避免覆盖整理产物）；
            字幕文件目标已存在时由调用方捕获并 warning 跳过（字幕是附属文件）。
            """
            abs_dst = os.path.abspath(dst)
            # shutil.move might overwrite dst file
            if os.path.exists(abs_dst):
                raise FileExistsError(f"File exists: {abs_dst}")
            if use_hardlink:
                # 硬链接模式：源文件保留不动，仅在目标位置创建一个新的硬链接
                try:
                    os.link(src, abs_dst)
                except OSError:
                    logger.warning(f"创建硬链接失败，回退为复制文件: '{src}' -> '{abs_dst}'")
                    shutil.copy2(src, abs_dst)
            else:
                shutil.move(src, abs_dst)
            src_rel = os.path.relpath(src)
            dst_name = os.path.basename(dst)
            logger.info(f"重命名文件: '{src_rel}' -> '...{os.sep}{dst_name}'")
            # 目前StreamHandler并未设置filter，为了避免显示中出现重复的日志，这里暂时只能用debug级别
            filemove_logger.debug(f'移动（重命名）文件: \n  原路径: "{src}"\n  新路径: "{abs_dst}"')

        moved_files = []
        src_dir = os.path.dirname(self.files[0])
        if len(self.files) == 1:
            fullpath = self.files[0]
            ext = os.path.splitext(fullpath)[1]
            newpath = os.path.join(self.save_dir, self.basename + ext)
            move_file(fullpath, newpath)
            moved_files.append((fullpath, newpath))
        else:
            for i, fullpath in enumerate(self.files, start=1):
                ext = os.path.splitext(fullpath)[1]
                newpath = os.path.join(self.save_dir, self.basename + f"-CD{i}" + ext)
                move_file(fullpath, newpath)
                moved_files.append((fullpath, newpath))

        # 移动匹配的字幕文件（基于番号模糊匹配：IPZ-380 == ipz380 == ipz00380）
        if Cfg().summarizer.match_subtitles:
            movie_norm_id = normalize_id(self.dvdid)
            if movie_norm_id:
                sub_dir = os.path.dirname(self.files[0])
                if os.path.isdir(sub_dir):
                    # 先过滤出目录中的字幕文件，没有则直接跳过后续匹配逻辑
                    sub_files = [
                        f
                        for f in sorted(os.listdir(sub_dir))
                        if os.path.isfile(os.path.join(sub_dir, f)) and os.path.splitext(f)[1].lower() in (".srt", ".ass")
                    ]
                    if sub_files:
                        # 收集所有番号匹配的字幕
                        matched_subs = []
                        for f in sub_files:
                            f_path = os.path.join(sub_dir, f)
                            f_stem, f_ext = os.path.splitext(f)
                            sub_id = get_id(f_stem)
                            if sub_id and normalize_id(sub_id) == movie_norm_id:
                                matched_subs.append((f_path, f_stem, f_ext))
                        # 多CD视频与字幕数量不匹配时仅 warning，仍按规则一起移动
                        if len(self.files) > 1 and len(matched_subs) not in (0, len(self.files)):
                            logger.warning(
                                f"多CD视频({len(self.files)}个)与匹配字幕({len(matched_subs)}个)数量不一致，仍将一起移动"
                            )
                        for f_path, f_stem, f_ext in matched_subs:
                            if len(self.files) == 1:
                                target_basename = self.basename
                            else:
                                target_basename = self.basename
                                cd_m = re.search(r"cd(\d+)$", f_stem, re.I)
                                if cd_m:
                                    target_basename += f"-CD{cd_m.group(1)}"
                            new_sub_path = os.path.join(self.save_dir, target_basename + f_ext.lower())
                            try:
                                move_file(f_path, new_sub_path)
                                logger.info(f"已移动字幕文件: '{f_path}'")
                                moved_files.append((f_path, new_sub_path))
                            except FileExistsError:
                                logger.warning(f"字幕文件已存在，跳过: '{new_sub_path}'")

        # 清理空目录：放在所有文件移动之后，避免提前删除仍含字幕的源目录
        try:
            if os.path.isdir(src_dir) and len(os.listdir(src_dir)) == 0:
                os.rmdir(src_dir)
        except OSError:
            pass

        return moved_files


class GenreMap(dict):
    """genre的映射表"""

    def __init__(self, file):
        genres = {}
        with open(resource_path(file), newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.DictReader(csvfile)
            try:
                for row in reader:
                    # 优先使用 zh_cn 作为翻译结果，否则回退 translate 列
                    translate = row.get("zh_cn") or row.get("translate")
                    if not translate:
                        continue
                    # 支持多列作为映射键（id、繁中、日文等），zh_cn 仅作为翻译输出不作为键
                    for key in ("id", "zh_tw", "ja"):
                        if row.get(key):
                            for value in row[key].split(","):
                                value = value.strip()
                                if value:
                                    genres[value] = translate
            except UnicodeDecodeError:
                logger.error("CSV file must be saved as UTF-8-BOM to edit is in Excel")
            except KeyError:
                logger.error("The columns 'id' and 'translate' must exist in the csv file")
        self.update(genres)

    def map(self, ls):
        """将列表ls按照内置的映射进行替换：保留映射表中不存在的键，删除值为空的键"""
        mapped = [self.get(i, i) for i in ls]
        cleaned = [i for i in mapped if i]  # 译文为空表示此genre应当被删除
        # 保持顺序去重
        return list(dict.fromkeys(cleaned))
