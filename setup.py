import os

from cx_Freeze import Executable, setup

# https://github.com/marcelotduarte/cx_Freeze/issues/1288
base = None

proj_root = os.path.abspath(os.path.dirname(__file__))


include_files: list[tuple[str, str]] = []

# 默认模板配置（随包发布）
_default_cfg = f"{proj_root}/config_default.yml"
if os.path.exists(_default_cfg):
    include_files.append((_default_cfg, "config_default.yml"))

# 用户配置（可选，存在才打包到产物目录）
_user_cfg = f"{proj_root}/config.yml"
if os.path.exists(_user_cfg):
    include_files.append((_user_cfg, "config.yml"))

# 静态资源目录
for _sub in ("data", "image"):
    _sub_dir = f"{proj_root}/{_sub}"
    if os.path.isdir(_sub_dir):
        include_files.append((_sub_dir, _sub))

# 如果有 VERSION 文件（CI 构建时写入），将其打入产物以支持版本识别
version_file_src = f"{proj_root}/javsp/VERSION"
version_file_dst = "javsp/VERSION"
if os.path.exists(version_file_src):
    include_files.append((version_file_src, version_file_dst))

includes = []

for file in os.listdir("javsp/web"):
    name, ext = os.path.splitext(file)
    if ext == ".py":
        includes.append("javsp.web." + name)

packages = [
    "pendulum",  # pydantic_extra_types depends on pendulum
]

build_exe = {
    "include_files": include_files,
    "includes": includes,
    "excludes": ["unittest"],
    "packages": packages,
    "silent": True,
}

javsp = Executable(
    "./javsp/__main__.py",
    target_name="JavSP-bin",
    base=base,
    icon="./image/JavSP.ico",
)

setup(name="JavSP", options={"build_exe": build_exe}, executables=[javsp])
