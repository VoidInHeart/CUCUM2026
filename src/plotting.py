"""可复用的 Matplotlib 中文字体和文件输出设置。"""
from pathlib import Path
import os
import logging
import tempfile

# 避免写用户目录，并支持无桌面环境下批量绘图。
os.environ.setdefault("MPLCONFIGDIR", str(Path(__file__).resolve().parents[1] / "tmp" / "matplotlib"))
import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager, pyplot as plt


def configure_chinese() -> str:
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    candidates = ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "Source Han Sans SC", "SimSun"]
    installed = {font.name for font in font_manager.fontManager.ttflist}
    selected = next((font for font in candidates if font in installed), None)
    if selected is None:
        raise RuntimeError("visualization: 未找到中文字体，请安装微软雅黑、黑体或 Noto Sans CJK SC")
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": [selected],
                         "axes.unicode_minus": False, "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.grid": True, "grid.alpha": 0.2,
                         "savefig.dpi": 180, "pdf.fonttype": 42})
    return selected


def save_figure(fig, directory: Path, name: str) -> list[Path]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    temporary = []
    try:
        # Windows预览器可能映射PDF，直接截断原文件会失败；先完整渲染再替换。
        # 临时文件直接放在输出目录，继承其ACL；不继承Python 3.13私有临时目录的权限。
        for suffix in ("png", "pdf"):
            with tempfile.NamedTemporaryFile(dir=directory, prefix=f".{name}.", suffix=f".{suffix}", delete=False) as handle:
                staged = Path(handle.name)
            temporary.append(staged)
            fig.savefig(staged, bbox_inches="tight")
            paths.append(directory / f"{name}.{suffix}")
        for staged, path in zip(temporary, paths):
            os.replace(staged, path)
    finally:
        for staged in temporary:
            staged.unlink(missing_ok=True)
        plt.close(fig)
    return paths
