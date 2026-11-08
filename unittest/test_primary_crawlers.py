"""JavDB 演员解析回归测试，不访问网络。"""

import pytest
from lxml.html import fromstring

from javsp.datatype import MovieInfo
from javsp.web import javdb


@pytest.mark.parametrize(
    "actors",
    [
        '<a class="actor-female">白咲璃音</a><a>男演员</a>',
        '<a>男演员</a><strong>♂</strong><a>白咲璃音</a><strong> ♀ </strong>',
        '<a>未标注性别的演员</a><a>白咲璃音</a><strong>♀</strong>',
    ],
    ids=["current", "legacy", "missing-gender"],
)
def test_javdb_actress(monkeypatch, actors):
    pages = iter([
        fromstring('<a class="box" href="https://javdb.com/v/test">'
                   '<div class="video-title"><strong>MIFD-670</strong></div></a>'),
        fromstring(f"""<html><body><section><div><div class="video-detail">
            <h2><strong class="current-title">MIFD-670 测试标题</strong></h2>
            <img class="video-cover" src="https://example.test/cover.jpg">
            <nav class="panel movie-panel-info">
                <div><strong>番號:</strong><span>MIFD-670</span></div>
                <div><strong>日期:</strong><span>2026-01-01</span></div>
                <div><strong>時長:</strong><span>120 分鍾</span></div>
                <div><strong>演員:</strong><span>{actors}</span></div>
            </nav>
        </div></div></section></body></html>"""),
    ])
    monkeypatch.setattr(javdb, "get_html_wrapper", lambda url: next(pages))
    movie = MovieInfo("MIFD-670")
    javdb.parse_data(movie)
    assert movie.actress == ["白咲璃音"]
