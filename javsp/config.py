import logging
import os
import sys
from argparse import ArgumentParser, RawTextHelpFormatter
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypeAlias

import yaml
from confz import BaseConfig, CLArgSource, EnvSource, FileSource
from pydantic import ByteSize, Field, NonNegativeInt, PositiveInt, model_validator
from pydantic_core import Url
from pydantic_extra_types.pendulum_dt import Duration

from javsp.lib import resource_path

_logger = logging.getLogger(__name__)

DEFAULT_CONFIG_FILE = "config_default.yml"
USER_CONFIG_FILE = "config.yml"


class Scanner(BaseConfig):
    ignored_id_pattern: list[str]
    input_directory: Path | None = None
    filename_extensions: list[str]
    ignored_folder_name_pattern: list[str]
    minimum_size: ByteSize
    skip_nfo_dir: bool
    manual: bool


class CrawlerID(StrEnum):
    avsox = "avsox"
    avwiki = "avwiki"
    dl_getchu = "dl_getchu"
    fanza = "fanza"
    fc2 = "fc2"
    fc2fan = "fc2fan"
    fc2ppvdb = "fc2ppvdb"
    gyutto = "gyutto"
    jav321 = "jav321"
    javbus = "javbus"
    javdb = "javdb"
    javlib = "javlib"
    javmenu = "javmenu"
    mgstage = "mgstage"
    njav = "njav"
    prestige = "prestige"


class Network(BaseConfig):
    proxy_server: Url | None
    retry: NonNegativeInt = 3
    timeout: Duration
    proxy_free: dict[str, Url]

    @model_validator(mode="before")
    @classmethod
    def filter_invalid_proxy_free(cls, data):
        valid_keys = {e.value for e in CrawlerID}
        if isinstance(data, dict):
            proxy_free = data.get("proxy_free", {})
            invalid_keys = [k for k in proxy_free if k not in valid_keys]
            if invalid_keys:
                _logger.warning(f"配置的免代理站点无效，已自动忽略: {', '.join(invalid_keys)}")
                data["proxy_free"] = {k: v for k, v in proxy_free.items() if k in valid_keys}
        return data


class CrawlerSelect(BaseConfig):
    normal: list[str]
    fc2: list[str]
    cid: list[str]
    getchu: list[str]
    gyutto: list[str]

    @model_validator(mode="before")
    @classmethod
    def filter_invalid_crawlers(cls, data):
        valid_ids = {e.value for e in CrawlerID}
        all_invalid = []
        if isinstance(data, dict):
            for attr in ("normal", "fc2", "cid", "getchu", "gyutto"):
                original = data.get(attr, [])
                valid = [c for c in original if c in valid_ids]
                invalid = [c for c in original if c not in valid_ids]
                if invalid:
                    all_invalid.extend(invalid)
                data[attr] = valid
            if all_invalid:
                _logger.warning(f"配置的抓取器无效，已自动忽略: {', '.join(all_invalid)}")
        return data

    def items(self) -> list[tuple[str, list[str]]]:
        return [
            ("normal", self.normal),
            ("fc2", self.fc2),
            ("cid", self.cid),
            ("getchu", self.getchu),
            ("gyutto", self.gyutto),
        ]

    def __getitem__(self, index) -> list[str]:
        if index in ("normal", "fc2", "cid", "getchu", "gyutto"):
            return getattr(self, index)
        raise Exception("Unknown crawler type")


class MovieInfoField(StrEnum):
    dvdid = "dvdid"
    cid = "cid"
    url = "url"
    plot = "plot"
    cover = "cover"
    big_cover = "big_cover"
    genre = "genre"
    genre_id = "genre_id"
    genre_norm = "genre_norm"
    score = "score"
    title = "title"
    ori_title = "ori_title"
    magnet = "magnet"
    serial = "serial"
    actress = "actress"
    actress_pics = "actress_pics"
    director = "director"
    duration = "duration"
    producer = "producer"
    publisher = "publisher"
    uncensored = "uncensored"
    publish_date = "publish_date"
    preview_pics = "preview_pics"
    preview_video = "preview_video"


class UseJavDBCover(StrEnum):
    yes = "yes"
    no = "no"
    fallback = "fallback"


class Crawler(BaseConfig):
    selection: CrawlerSelect
    required_keys: list[MovieInfoField]
    hardworking: bool
    respect_site_avid: bool
    fc2fan_local_path: Path | None
    sleep_after_scraping: Duration
    use_javdb_cover: UseJavDBCover
    normalize_actress_name: bool


class MovieDefault(BaseConfig):
    title: str
    actress: str
    series: str
    director: str
    producer: str
    publisher: str


class PathSummarize(BaseConfig):
    output_folder_pattern: str
    basename_pattern: str
    length_maximum: PositiveInt
    length_by_byte: bool
    max_actress_count: PositiveInt = 10
    hard_link: bool


class TitleSummarize(BaseConfig):
    remove_trailing_actor_name: bool


class NFOSummarize(BaseConfig):
    basename_pattern: str
    title_pattern: str
    custom_genres_fields: list[str]
    custom_tags_fields: list[str]


class ExtraFanartSummarize(BaseConfig):
    enabled: bool
    scrap_interval: Duration


class SlimefaceEngine(BaseConfig):
    name: Literal["slimeface"]


class CoverCrop(BaseConfig):
    engine: SlimefaceEngine | None = None
    on_id_pattern: list[str]


class CoverSummarize(BaseConfig):
    basename_pattern: str
    highres: bool
    add_label: bool
    crop: CoverCrop


class FanartSummarize(BaseConfig):
    basename_pattern: str


class Summarizer(BaseConfig):
    default: MovieDefault
    censor_options_representation: list[str]
    title: TitleSummarize
    move_files: bool = True
    match_subtitles: bool = True
    filemove_log: bool = False
    path: PathSummarize
    nfo: NFOSummarize
    cover: CoverSummarize
    fanart: FanartSummarize
    extra_fanarts: ExtraFanartSummarize


class OpenAICompatibleEngine(BaseConfig):
    type: Literal["openai_compatible"]
    base_url: Url
    api_key: str
    model: str
    system_prompt: str = (
        "Translate the following Japanese text into Chinese. "
        "Keep non-Japanese text, names, and any content that does not look like Japanese unchanged. "
        "Reply with the translated text only, do not add any text that is not in the original content."
    )
    temperature: float = 0.3
    max_tokens: int = 2048


class AnthropicEngine(BaseConfig):
    type: Literal["anthropic"]
    base_url: Url = Url("https://api.anthropic.com/v1")
    api_key: str
    model: str = "claude-3-5-sonnet-20241022"
    system_prompt: str = (
        "Translate the following Japanese text into Chinese. "
        "Keep non-Japanese text, names, and any content that does not look like Japanese unchanged. "
        "Reply with the translated text only, do not add any text that is not in the original content."
    )
    max_tokens: int = 2048
    temperature: float = 0.3


class GoogleTranslateEngine(BaseConfig):
    """Google 翻译（免费，无需 API Key）"""

    type: Literal["google"]
    source_language: str = "auto"
    target_language: str = "zh-CN"


class BingTranslateEngine(BaseConfig):
    """Bing 翻译（免费，无需 API Key）"""

    type: Literal["bing"]
    source_language: str = "auto"
    target_language: str = "zh-Hans"


class AlibabaTranslateEngine(BaseConfig):
    """阿里翻译（免费，无需 API Key）"""

    type: Literal["alibaba"]
    source_language: str = "auto"
    target_language: str = "zh"


TranslateEngine: TypeAlias = (
    OpenAICompatibleEngine | AnthropicEngine | GoogleTranslateEngine | BingTranslateEngine | AlibabaTranslateEngine | None
)


class TranslateField(BaseConfig):
    title: bool = True
    plot: bool = True


class Translator(BaseConfig):
    engine: TranslateEngine = Field(default=None, discriminator="type")
    fields: TranslateField = TranslateField()


class Other(BaseConfig):
    interactive: bool
    check_update: bool
    auto_update: bool
    debug: bool = False
    auto_exit: bool = True


def _find_user_config() -> str | None:
    """查找用户配置文件 config.yml

    查找顺序（命中即返回）：
    1. 当前工作目录（CWD）：便于 pip 安装后用户在任意运行目录放置 config.yml
    2. 可执行文件所在目录（仅 frozen 模式，即 cx_Freeze 打包后）
    3. 源码根目录（开发模式 -e 安装时从仓库根目录读取）

    这样可以让用户配置文件"放在外面"，而不是被锁在 site-packages 内部。
    """
    candidates = [os.getcwd()]
    if getattr(sys, "frozen", False):
        candidates.append(os.path.dirname(sys.executable))
    # 开发模式回退：源码根目录（javsp 包的上一级）
    candidates.append(str(Path(__file__).resolve().parent.parent))
    for dir_path in candidates:
        candidate = os.path.join(dir_path, USER_CONFIG_FILE)
        if os.path.isfile(candidate):
            return candidate
    return None


def get_config_source():
    """构建配置源列表，使用缓存避免重复计算

    缓存一旦生成便不会刷新，因为配置源在程序启动时由命令行参数和文件决定，
    运行期间不会改变。如果未来需要动态刷新配置，需先置 _config_sources = None。
    """
    global _config_sources
    if _config_sources is not None:
        return _config_sources

    parser = ArgumentParser(
        prog="JavSP",
        description="汇总多站点数据的AV元数据刮削器",
        formatter_class=RawTextHelpFormatter,
        # 禁用前缀缩写匹配：避免 pytest 等工具传入的参数（如 --co）被误解析为
        # --config 的缩写而导致 SystemExit，从而破坏测试收集和模块导入。
        allow_abbrev=False,
    )
    parser.add_argument("-c", "--config", help="使用指定的配置文件")
    args, _ = parser.parse_known_args()
    sources = []

    # 1. 始终加载默认模板配置（已随 wheel 打包到 site-packages 根目录）
    default_config = resource_path(DEFAULT_CONFIG_FILE)
    sources.append(FileSource(file=default_config))

    # 2. 加载用户配置（如果存在且非空），覆盖默认值
    if args.config is not None:
        sources.append(FileSource(file=args.config))
    else:
        user_config = _find_user_config()
        if user_config is not None:
            try:
                with open(user_config, encoding="utf-8") as f:
                    if yaml.safe_load(f) is not None:
                        sources.append(FileSource(file=user_config))
            except Exception:
                pass

    # 3. 环境变量和命令行参数优先级最高
    sources.append(EnvSource(prefix="JAVSP_", allow_all=True, nested_separator="__"))
    sources.append(CLArgSource(prefix="o"))
    _config_sources = sources
    return sources


_config_sources = None


class Cfg(BaseConfig):
    scanner: Scanner
    network: Network
    crawler: Crawler
    summarizer: Summarizer
    translator: Translator
    other: Other
    CONFIG_SOURCES = get_config_source()
