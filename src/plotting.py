"""可复用的 Matplotlib 中文字体和文件输出设置。"""
from pathlib import Path
import os
import logging

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
    try:
        for suffix in ("png", "pdf"):
            path = directory / f"{name}.{suffix}"
            fig.savefig(path, bbox_inches="tight")
            paths.append(path)
    finally:
        plt.close(fig)
    return paths
