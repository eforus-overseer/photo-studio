"""Run explicitly on a desktop or under xvfb-run; excluded from headless default."""
import os
import time
import pytest
from PIL import Image

pytestmark = pytest.mark.skipif(os.environ.get('PHOTO_STUDIO_GUI_TESTS') != '1', reason='requires a desktop')


def test_desktop_flow(tmp_path, monkeypatch):
    from GUI import PhotoStudio
    import GUI
    folder = tmp_path / 'images'
    folder.mkdir()
    Image.new('RGB', (80, 60), (60, 90, 120)).save(folder / 'one.png')
    Image.new('RGB', (60, 80), (120, 90, 60)).save(folder / 'two.png')
    output = tmp_path / 'export'
    output.mkdir()
    dialogs, errors = [], []
    for name in ('showerror', 'showinfo', 'showwarning'):
        monkeypatch.setattr(GUI.messagebox, name, lambda *args, **kwargs: dialogs.append(args))
    app = PhotoStudio()
    app.report_callback_exception = lambda *args: errors.append(args)
    def until(predicate):
        deadline = time.monotonic() + 15
        while not predicate() and time.monotonic() < deadline:
            app.update()
            time.sleep(.03)
        assert predicate(), (errors, dialogs)
    try:
        app.load_folder(folder)
        until(lambda: app.original is not None)
        app.choose_effect('mirror')
        until(lambda: app.processed is not None)
        assert app.processed.size == (80, 60)
        app.choose_effect('edge')
        app.threshold.set(18)
        app.change_threshold(18)
        until(lambda: app.processed is not None and app.threshold_timer is None)
        app.select_all()
        app.destination.set(str(output))
        app.export()
        until(lambda: not app.exporting)
        assert len(list(output.glob('*.png'))) == 2
        app.reset_effect()
        assert app.effect is None and app.processed is None
        app.clear()
        assert not app.paths and app.original is None
        app.load_folder(folder)
        app.choose_effect('sepia')  # Effect selection while original is still loading.
        until(lambda: app.processed is not None)
        assert not errors
        assert len(dialogs) == 1  # Only the successful export dialog.
    finally:
        app.close()
