"""图表保存失败时保护原文件，并避免直接截断正在预览的PDF。"""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import Mock, patch

from src.plotting import save_figure


class FigureSaveTests(TestCase):
    def test_render_failure_preserves_both_previous_formats(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            for suffix in ("png", "pdf"):
                (directory/f"plot.{suffix}").write_bytes(b"previous")
            def render(path, **kwargs):
                Path(path).write_bytes(b"partial")
                if path.suffix == ".pdf": raise OSError("render failed")
            fig = Mock()
            fig.savefig.side_effect = render
            with patch("src.plotting.plt.close"), self.assertRaisesRegex(OSError, "render failed"):
                save_figure(fig, directory, "plot")
            self.assertEqual(sorted(p.name for p in directory.iterdir()), ["plot.pdf", "plot.png"])
            self.assertTrue(all(p.read_bytes() == b"previous" for p in directory.iterdir()))

    def test_success_replaces_files_from_same_directory_staging(self):
        with TemporaryDirectory() as folder:
            directory = Path(folder)
            fig = Mock()
            def render(path, **kwargs):
                self.assertEqual(path.parent, directory)
                self.assertTrue(path.name.startswith(".plot."))
                Path(path).write_bytes(b"complete")
            fig.savefig.side_effect = render
            with patch("src.plotting.plt.close") as close:
                paths = save_figure(fig, directory, "plot")
            close.assert_called_once_with(fig)
            self.assertEqual(paths, [directory/"plot.png", directory/"plot.pdf"])
            self.assertTrue(all(p.read_bytes() == b"complete" for p in paths))
            self.assertEqual(len(list(directory.iterdir())), 2)
