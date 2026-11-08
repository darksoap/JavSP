"""使用真实页面的精简结构，离线验证 JavDB/JavBus 的演员解析。"""

import pytest
from lxml import etree
from requests import Response

from javsp.datatype import Movie, MovieInfo
from javsp.nfo import write_nfo
from javsp.summarizer import info_summary
from javsp.web import javbus, javdb


def _response(url, markup):
    response = Response()
    response.status_code = 200
    response.url = url
    response._content = markup.encode("utf-8")
    return response


@pytest.fixture
def parse_javdb(monkeypatch):
    def parse(actors):
        search = _response(
            "https://javdb.com/search?q=MIFD-670",
            '<a class="box" href="/v/test"><div class="video-title"><strong>MIFD-670</strong></div></a>',
        )
        detail = _response(
            "https://javdb.com/v/test",
            f"""<html><body><section><div><div class="video-detail">
                <h2><strong class="current-title">MIFD-670 测试标题</strong></h2>
                <img class="video-cover" src="/cover.jpg">
                <nav class="panel movie-panel-info">
                    <div><strong>番號:</strong><span>MIFD-670</span></div>
                    <div><strong>日期:</strong><span>2026-01-01</span></div>
                    <div><strong>時長:</strong><span>120 分鍾</span></div>
                    <div><strong>演員:</strong><span class="value">{actors}</span></div>
                </nav>
            </div></div></section></body></html>""",
        )
        responses = iter((search, detail))
        monkeypatch.setattr(javdb.request, "get", lambda *args, **kwargs: next(responses))
        movie = MovieInfo("MIFD-670")
        javdb.parse_data(movie)
        return movie

    return parse


@pytest.mark.parametrize(
    ("actors", "expected"),
    [
        (
            '<a class="actor-female" href="/actors/f">白咲璃音</a>, '
            '<a href="/actors/m">男演员</a>',
            ["白咲璃音"],
        ),
        (
            '<a class="featured actor-female" href="/actors/f"><span> 白咲璃音 </span></a>, '
            '<a class="actor-female" href="/actors/f2">另一位女优</a>',
            ["白咲璃音", "另一位女优"],
        ),
        (
            '<a href="/actors/m">男演员</a><strong>♂</strong>'
            '<a href="/actors/f">白咲璃音</a><strong> ♀ </strong>',
            ["白咲璃音"],
        ),
        (
            '<a href="/actors/m">未标注性别的演员</a>'
            '<a href="/actors/f">白咲璃音</a><strong>♀</strong>',
            ["白咲璃音"],
        ),
        ('<a href="/actors/m">男演员</a><strong>♂</strong>', []),
        ('<a class="actor-female" href="/actors/f"> </a>', []),
    ],
    ids=["current", "multiple-and-nested", "legacy", "missing-gender", "male-only", "empty-name"],
)
def test_javdb_actress(parse_javdb, actors, expected):
    assert parse_javdb(actors).actress == expected


@pytest.fixture
def parse_javbus(monkeypatch):
    def parse(picture):
        detail = _response(
            "https://www.javbus.com/MIFD-670",
            f"""<html><head><title>MIFD-670 - JavBus</title></head><body>
                <div class="container">
                    <h3>MIFD-670 测试标题</h3>
                    <a class="bigImage"><img src="/cover.jpg"></a>
                    <div class="col-md-3 info">
                        <p><span>識別碼:</span><span>MIFD-670</span></p>
                        <p><span>發行日期:</span> 2026-01-01</p>
                        <p><span>長度:</span> 120分鐘</p>
                    </div>
                    <a class="avatar-box" href="/star/1466"><div class="photo-frame">
                        <img src="{picture}" title="白咲璃音">
                    </div><span>白咲璃音</span></a>
                </div>
            </body></html>""",
        )
        monkeypatch.setattr(javbus, "request_get", lambda *args, **kwargs: detail)
        movie = MovieInfo("MIFD-670")
        javbus.parse_data(movie)
        return movie

    return parse


@pytest.mark.parametrize("picture", ["/actress.jpg", "/nowprinting.gif"])
def test_javbus_actress_with_or_without_portrait(parse_javbus, picture):
    movie = parse_javbus(picture)
    assert movie.actress == ["白咲璃音"]
    expected = {} if picture.endswith("nowprinting.gif") else {"白咲璃音": "https://www.javbus.com/actress.jpg"}
    assert movie.actress_pics == expected


@pytest.mark.parametrize("javdb_actors", ['<a class="actor-female" href="/actors/f">白咲璃音</a>', ""])
def test_primary_crawlers_actress_reaches_nfo(parse_javdb, parse_javbus, javdb_actors, tmp_path):
    sources = {"javdb": parse_javdb(javdb_actors), "javbus": parse_javbus("/nowprinting.gif")}
    movie = Movie("MIFD-670")
    assert info_summary(movie, sources) is None
    assert movie.info.actress == ["白咲璃音"]
    assert movie.info.field_sources["actress"] == ("javdb" if javdb_actors else "javbus")
    nfo = tmp_path / "movie.nfo"
    write_nfo(movie.info, nfo)
    assert etree.parse(str(nfo)).xpath("/movie/actor/name/text()") == ["白咲璃音"]
