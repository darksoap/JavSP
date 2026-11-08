![JavSP](./image/JavSP.svg)

# Jav Scraper Package - Continuum

> 本项目是 [JavSP](https://github.com/Yuukiy/JavSP) 的延续版本（community continue），在原项目基础上进行维护和改进。

**汇总多站点数据的AV元数据刮削器**

提取影片文件名中的番号信息，自动抓取并汇总多个站点数据的 AV 元数据，按照指定的规则分类整理影片文件，并创建供 Emby、Jellyfin、Kodi 等软件使用的元数据文件

**WebUI**: UI界面不是[此项目的目标](https://github.com/Yuukiy/JavSP/issues/148)。

**i18n**: This project currently supports only Chinese. However, if you're willing, you can [vote here](https://github.com/Yuukiy/JavSP/discussions/157) for the language you'd like to see added

![Python 3.14](https://img.shields.io/badge/python-3.14-green.svg)
[![稳定版](https://img.shields.io/github/v/release/darksoap/JavSP)](https://github.com/darksoap/JavSP/releases/latest)
[![尝鲜版 (CI)](https://img.shields.io/github/actions/workflow/status/darksoap/JavSP/build.yml?label=%E5%B0%9D%E9%B2%9C%E7%89%88%20%28CI%29)](https://github.com/darksoap/JavSP/actions/workflows/build.yml)
![License](https://img.shields.io/github/license/Yuukiy/JavSP)
[![LICENSE](https://img.shields.io/badge/license-Anti%20996-blue.svg)](https://github.com/996icu/996.ICU/blob/master/LICENSE)
[![996.icu](https://img.shields.io/badge/link-996.icu-red.svg)](https://996.icu)

## 功能特点

下面这些是一些已实现或待实现的功能，在逐渐实现和完善，如果想到新的功能点也会加进来。

- [x] 自动识别影片番号
- [x] 支持处理影片分片
- [x] 汇总多个站点的数据生成NFO数据文件
- [x] 每天自动对站点抓取器进行测试
- [x] 多线程并行抓取
- [x] 下载高清封面
- [x] 基于AI人体分析裁剪素人等非常规封面的海报
- [x] 自动检查和更新新版本
- [x] 翻译标题和剧情简介
- [x] 匹配本地字幕
- [ ] 使用小缩略图创建文件夹封面
- [ ] 保持不同站点间 genre 分类的统一
- [ ] 不同的运行模式（抓取数据+整理，仅抓取数据）
- [ ] 可选：所有站点均抓取失败时由人工介入

## 迁移

功能修改日志：[ChangeLog](./CHANGELOG.md)

## [安装并运行JavSP](https://github.com/Yuukiy/JavSP/wiki/%E5%AE%89%E8%A3%85%E5%B9%B6%E8%BF%90%E8%A1%8CJavSP)

## 使用

软件开箱即用。如果想让软件更符合你的使用需求，也许你需要更改配置文件:

> 在程序同目录下创建 `config.yml`，只需写需要覆盖的配置项即可（未配置的项使用 `config_default.yml` 中的默认值）。

此外软件也支持通过 `-c` 参数指定配置文件路径，以及从环境变量（`JAVSP_` 前缀）和命令行参数覆盖配置。运行 `JavSP -h` 查看支持的参数列表

更详细的使用说明请前往 [JavSP Wiki](https://github.com/Yuukiy/JavSP/wiki) 查看

如果使用的时候遇到问题也欢迎给我反馈😊

## 问题反馈

如果使用中遇到了 Bug，请[前往 Issue 区反馈](https://github.com/darksoap/JavSP/issues)（提问前请先搜索是否已有类似问题）

## 参与贡献

此项目不需要捐赠。如果你想要帮助改进这个项目，欢迎通过以下方式参与进来（并不仅局限于代码）：

- 帮助撰写和改进Wiki
- 帮助完善单元测试数据（不必非要写代码，例如如果你发现有某系列的番号识别不准确，总结一下提issue也是很好的）
- 帮助翻译 genre
- Bugfix / 新功能？欢迎发 Pull Request
- 要不考虑点个 Star ?（我会很开心的）

## 许可

此项目的所有权利与许可受 GPL-3.0 License 与 [Anti 996 License](https://github.com/996icu/996.ICU/blob/master/LICENSE_CN) 共同限制。此外，如果你使用此项目，表明你还额外接受以下条款：

- 本软件仅供学习 Python 和技术交流使用
- 请勿在微博、微信等墙内的公共社交平台上宣传此项目
- 用户在使用本软件时，请遵守当地法律法规
- 禁止将本软件用于商业用途

