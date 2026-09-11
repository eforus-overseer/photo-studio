"""Capture the real desktop window (macOS, a desktop, and pyobjc-framework-Cocoa)."""
import sys
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from AppKit import NSApplication, NSBitmapImageFileTypeJPEG
from GUI import PhotoStudio

ROOT = Path(__file__).resolve().parents[1]
app = PhotoStudio(ROOT / 'docs/samples/cheerful-puppy.png')
app.geometry('1380x900+20+40')
errors = []
def report(*args):
    traceback.print_exception(*args)
    errors.append(repr(args[1]))
app.report_callback_exception = report
steps = [('studio-workspace.jpg', None, 'Original'),
         ('studio-compare.jpg', 'film', 'Compare'),
         ('studio-segments.jpg', 'segments', 'Result'),
         ('studio-cutout.jpg', 'cutout', 'Result')]


def capture():
    if errors:
        raise RuntimeError(errors)
    if app.original is None or (app.effect and app.processed is None):
        app.after(100, capture)
        return
    filename, effect, view = steps.pop(0)
    app.lift()
    app.focus_force()
    app.update()
    bbox = (app.winfo_rootx(), app.winfo_rooty(), app.winfo_rootx() + app.winfo_width(), app.winfo_rooty() + app.winfo_height())
    windows = [w for w in NSApplication.sharedApplication().windows() if w.title() == app.title()]
    if not windows:
        raise RuntimeError('Editor window not found')
    view = windows[0].contentView()
    bitmap = view.bitmapImageRepForCachingDisplayInRect_(view.bounds())
    view.cacheDisplayInRect_toBitmapImageRep_(view.bounds(), bitmap)
    data = bitmap.representationUsingType_properties_(NSBitmapImageFileTypeJPEG, {})
    data.writeToFile_atomically_(str(ROOT / 'docs/media' / filename), True)
    print('Captured', filename, flush=True)
    if steps:
        prepare()
    else:
        app.close()


def prepare():
    filename, effect, view = steps[0]
    app.view.set(view)
    if effect:
        if effect == 'cutout':
            app.roi = (.28, .04, .69, .95)
        app.choose_effect(effect)
    else:
        app.schedule_render()
    app.after(1600, capture)

app.after(2200, prepare)
app.after(120000, lambda: (print('Capture timed out', flush=True), app.close()))
app.mainloop()
if errors:
    raise RuntimeError(errors)
