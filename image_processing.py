"""Image operations and safe batch export, independent of the desktop interface."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff', '.webp'}
FORMATS = {'.jpg': 'JPEG', '.jpeg': 'JPEG', '.png': 'PNG', '.bmp': 'BMP',
           '.gif': 'GIF', '.tif': 'TIFF', '.tiff': 'TIFF', '.webp': 'WEBP'}


@dataclass(frozen=True)
class Effect:
    key: str
    name: str
    group: str
    description: str


EFFECTS = (
    Effect('rotate', 'Rotate 180°', 'Transform', 'Turn the image upside down. Keep every pixel.'),
    Effect('mirror', 'Mirror', 'Transform', 'Flip the image horizontally, from left to right.'),
    Effect('resize', 'Half size', 'Transform', 'The original resize effect: grayscale at half the width and height.'),
    Effect('edge', 'Edge recognition', 'Creative', 'Trace changes in luminance. A lower threshold reveals more edges.'),
    Effect('primary', 'Primary colors', 'Creative', 'Reduce each color channel to black or full intensity for a graphic palette.'),
    Effect('halftone', 'Halftone', 'Creative', 'Translate tones into the original two-by-two black-and-white dot patterns.'),
    Effect('blur', 'Gaussian blur', 'Refine', 'Soften fine detail with the original 20-pixel Gaussian blur.'),
    Effect('minimum', 'Minimum filter', 'Refine', 'Expand dark details using a seven-by-seven neighborhood.'),
    Effect('sharpen', 'Sharpen', 'Refine', 'Recover definition with an unsharp mask.'),
    Effect('contour', 'Contour', 'Creative', 'Render light outlines around the shapes in your image.'),
    Effect('detail', 'Detail', 'Refine', 'Emphasize texture and subtle local detail.'),
    Effect('enhance', 'Edge enhance+', 'Refine', 'Give boundaries and fine structures stronger definition.'),
    Effect('emboss', 'Emboss', 'Creative', 'Turn light and shadow into a sculpted relief.'),
    Effect('smooth', 'Kernel smooth', 'Refine', 'A gentle weighted three-by-three smoothing kernel.'),
    Effect('mono', 'Silver monochrome', 'Color & tone', 'Clean black and white with a gentle contrast lift.'),
    Effect('sepia', 'Warm sepia', 'Color & tone', 'A warm photographic print, from cocoa shadows to cream highlights.'),
    Effect('film', 'Faded film', 'Color & tone', 'Muted color, lifted shadows, and a restrained warm cast.'),
    Effect('duotone', 'Ink & sand', 'Color & tone', 'Deep blue-green shadows and warm sand highlights.'),
    Effect('vignette', 'Soft vignette', 'Color & tone', 'A gradual falloff at the edges to draw attention inward.'),
    Effect('posterize', 'Posterize', 'Creative', 'Four levels per channel for bold shapes and reduced color.'),
    Effect('solarize', 'Solarize', 'Creative', 'Invert the brightest tones for a photographic darkroom effect.'),
    Effect('autocontrast', 'Auto contrast', 'Refine', 'Stretch the tonal range while trimming the outer one percent.'),
    Effect('segments', 'Color segmentation', 'Segmentation', 'Group similar colors into six smooth palette regions. Color-based, not object recognition.'),
    Effect('cutout', 'Foreground cutout', 'Segmentation', 'Draw a box around the subject. GrabCut separates it from the background; exports use transparent PNG.'),
)
EFFECT_BY_KEY = {effect.key: effect for effect in EFFECTS}


def read_image(path: str | Path) -> Image.Image:
    """Load the first frame, honor EXIF orientation, and normalize input modes."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        alpha = 'A' in image.getbands() or 'transparency' in image.info
        return image.convert('RGBA' if alpha else 'RGB')


def list_images(directory: str | Path) -> list[Path]:
    return sorted((p for p in Path(directory).expanduser().iterdir()
                   if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS),
                  key=lambda p: p.name.casefold())


def _edges(image: Image.Image, threshold: int) -> Image.Image:
    gray = image.convert('L')
    w, h = gray.size
    result = Image.new('L', (w, h))
    if w < 2 or h < 2:
        return result
    center = gray.crop((0, 1, w - 1, h))
    horizontal = ImageChops.difference(center, gray.crop((1, 1, w, h)))
    vertical = ImageChops.difference(center, gray.crop((0, 0, w - 1, h - 1)))
    edges = ImageChops.lighter(horizontal, vertical).point(lambda v: 255 if v > threshold else 0)
    result.paste(edges, (0, 1))
    return result


def _halftone(image: Image.Image) -> Image.Image:
    # Match the legacy luminance formula and pattern; clamp odd edge blocks.
    rgb = image.convert('RGB')
    w, h = rgb.size
    source = rgb.load()
    output = Image.new('L', (w, h))
    pixels = output.load()
    for y in range(0, h, 2):
        for x in range(0, w, 2):
            values = [source[min(x + dx, w - 1), min(y + dy, h - 1)]
                      for dy in range(2) for dx in range(2)]
            tone = sum(r * .299 + g * .587 + b * .114 for r, g, b in values) / 4
            pattern = ((255, 255, 255, 255) if tone > 223 else
                       (255, 255, 0, 255) if tone > 159 else
                       (255, 0, 0, 255) if tone > 95 else
                       (0, 0, 255, 0) if tone > 32 else (0, 0, 0, 0))
            for dy in range(2):
                for dx in range(2):
                    if x + dx < w and y + dy < h:
                        pixels[x + dx, y + dy] = pattern[dy * 2 + dx]
    return output.convert('RGB')


def foreground_cutout(image: Image.Image, roi=None) -> Image.Image:
    """GrabCut with a normalized subject rectangle; estimate a mask at <=1000 px."""
    import cv2
    import numpy as np
    if min(image.size) < 8:
        raise ValueError('Foreground cutout needs an image at least 8 × 8 pixels.')
    roi = roi or (.04, .04, .96, .96)
    if len(roi) != 4 or not (0 <= roi[0] < roi[2] <= 1 and 0 <= roi[1] < roi[3] <= 1):
        raise ValueError('Select a rectangle around the subject inside the image.')
    reduced = image.convert('RGB')
    reduced.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
    w, h = reduced.size
    left, top = max(1, int(roi[0] * w)), max(1, int(roi[1] * h))
    right, bottom = min(w - 1, int(roi[2] * w)), min(h - 1, int(roi[3] * h))
    if right - left < 2 or bottom - top < 2:
        raise ValueError('Draw a larger subject rectangle.')
    mask = np.zeros((h, w), np.uint8)
    try:
        cv2.grabCut(np.array(reduced), mask, (left, top, right - left, bottom - top),
                    np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64), 5, cv2.GC_INIT_WITH_RECT)
    except cv2.error as error:
        raise ValueError('Could not separate the subject. Try a tighter rectangle with background outside it.') from error
    binary = np.where((mask == 1) | (mask == 3), 255, 0).astype('uint8')
    if not binary.any():
        raise ValueError('No foreground found. Draw a box around a distinct subject and try again.')
    alpha = Image.fromarray(binary).resize(image.size, Image.Resampling.LANCZOS)
    output = image.convert('RGBA')
    alpha = ImageChops.multiply(alpha, output.getchannel('A'))
    output.putalpha(alpha)
    return output


def apply_effect(image: Image.Image, effect: str, threshold: int = 40, roi=None) -> Image.Image:
    """Apply one effect to the original at full resolution; never mutate it."""
    if effect not in EFFECT_BY_KEY:
        raise ValueError(f'Unknown effect: {effect}')
    if effect == 'edge' and (isinstance(threshold, bool) or not isinstance(threshold, int)
                             or not 1 <= threshold <= 199):
        raise ValueError('Threshold must be a whole number between 1 and 199.')
    has_alpha = 'A' in image.getbands() or 'transparency' in image.info
    source = image.convert('RGBA' if has_alpha else 'RGB')
    if effect == 'cutout':
        return foreground_cutout(source, roi)
    if effect == 'rotate':
        return source.transpose(Image.Transpose.ROTATE_180)
    if effect == 'mirror':
        return ImageOps.mirror(source)
    alpha = source.getchannel('A') if has_alpha else None
    rgb = source.convert('RGB')
    if effect == 'resize':
        # Correct the legacy missing-parentheses overflow; omit unmatched odd edges.
        w, h = rgb.size
        crop = rgb.crop((0, 0, max(1, w - w % 2), max(1, h - h % 2)))
        result = crop.convert('L').resize((max(1, w // 2), max(1, h // 2)), Image.Resampling.BOX)
        if alpha is not None:
            alpha = alpha.crop((0, 0, crop.width, crop.height)).resize(result.size, Image.Resampling.BOX)
    elif effect == 'edge':
        result = _edges(rgb, threshold)
    elif effect == 'primary':
        result = rgb.point(lambda v: 255 if v > 127 else 0)
    elif effect == 'halftone':
        result = _halftone(rgb)
    elif effect == 'mono':
        result = ImageEnhance.Contrast(rgb.convert('L')).enhance(1.12)
    elif effect == 'sepia':
        result = ImageOps.colorize(rgb.convert('L'), '#302015', '#f7e7c6')
    elif effect == 'duotone':
        result = ImageOps.colorize(rgb.convert('L'), '#163638', '#efd4a4')
    elif effect == 'film':
        muted = ImageEnhance.Color(rgb).enhance(.72)
        channels = muted.split()
        result = Image.merge('RGB', tuple(ch.point(lambda v, offset=offset: int(v * .88 + offset))
                                         for ch, offset in zip(channels, (25, 20, 16))))
    elif effect == 'vignette':
        import numpy as np
        y, x = np.ogrid[-1:1:complex(rgb.height), -1:1:complex(rgb.width)]
        strength = np.clip(1 - .35 * (x*x + y*y), .35, 1)
        result = Image.fromarray((np.array(rgb) * strength[..., None]).clip(0, 255).astype('uint8'))
    elif effect == 'posterize':
        result = ImageOps.posterize(rgb, 2)
    elif effect == 'solarize':
        result = ImageOps.solarize(rgb, 160)
    elif effect == 'autocontrast':
        result = ImageOps.autocontrast(rgb, cutoff=1)
    elif effect == 'segments':
        result = rgb.filter(ImageFilter.MedianFilter(5)).quantize(colors=6, method=Image.Quantize.MEDIANCUT).convert('RGB')
    else:
        filters = {
            'blur': ImageFilter.GaussianBlur(20), 'minimum': ImageFilter.MinFilter(7),
            'sharpen': ImageFilter.UnsharpMask(), 'contour': ImageFilter.CONTOUR,
            'detail': ImageFilter.DETAIL, 'enhance': ImageFilter.EDGE_ENHANCE_MORE,
            'emboss': ImageFilter.EMBOSS,
            'smooth': ImageFilter.Kernel((3, 3), [1, 2, 1, 2, 4, 2, 1, 2, 1], 16),
        }
        result = rgb.filter(filters[effect])
    if alpha is not None:
        result = result.convert('RGBA')
        result.putalpha(alpha)
    return result


def save_image(image: Image.Image, path: str | Path, *, exclusive: bool = False) -> None:
    path = Path(path)
    fmt = FORMATS.get(path.suffix.lower())
    if not fmt:
        raise ValueError(f'Unsupported output extension: {path.suffix}')
    output = image
    if fmt in {'JPEG', 'BMP'}:
        if 'A' in image.getbands():
            output = Image.new('RGB', image.size, 'white')
            output.paste(image, mask=image.getchannel('A'))
        else:
            output = image.convert('RGB')
    # An exclusive open prevents an existing file from ever being overwritten.
    created = False
    try:
        with path.open('xb' if exclusive else 'wb') as stream:
            created = True
            output.save(stream, format=fmt, **({'quality': 95} if fmt == 'JPEG' else {}))
    except Exception:
        if exclusive and created:
            path.unlink(missing_ok=True)
        raise


@dataclass
class BatchResult:
    saved: list[Path] = field(default_factory=list)
    errors: list[tuple[Path, str]] = field(default_factory=list)


def export_batch(paths: list[Path], destination: str | Path, effect: str,
                 threshold: int = 40, progress: Callable[[int, int], None] | None = None, roi=None) -> BatchResult:
    destination = Path(destination).expanduser()
    if not destination.is_dir():
        raise ValueError('Choose an existing output folder.')
    report = BatchResult()
    # Preserve order while removing duplicate selections.
    sources = list(dict.fromkeys(Path(p) for p in paths))
    for index, source in enumerate(sources):
        try:
            result = apply_effect(read_image(source), effect, threshold, roi)
            serial = 1
            while True:
                suffix = '' if serial == 1 else f'_{serial}'
                extension = '.png' if effect == 'cutout' else source.suffix.lower()
                target = destination / f'{source.stem}_processed{suffix}{extension}'
                try:
                    save_image(result, target, exclusive=True)
                    report.saved.append(target)
                    break
                except FileExistsError:
                    serial += 1
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            report.errors.append((source, str(error)))
        if progress:
            progress(index + 1, len(sources))
    return report


# Keep the original processing entry points available to existing Python callers.
def _legacy(source, target, effect, threshold=40):
    result = apply_effect(read_image(source), effect, threshold)
    if target:
        save_image(result, target)
        return None
    return result


def rotatePicture(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'rotate')


def mirrorPicture(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'mirror')


def resizePicture(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'resize')


def edge(sourceImagePath, targetImagePath='', threshold=40):
    return _legacy(sourceImagePath, targetImagePath, 'edge', threshold)


def MyAlgorithm1(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'primary')


def MyAlgorithm2(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'halftone')


def gaussBlur(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'blur')


def minFilter(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'minimum')


def sharpen(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'sharpen')


def contour(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'contour')


def detail(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'detail')


def edgeEnhanceMore(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'enhance')


def emboss(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'emboss')


def kernelSmooth(sourceImagePath, targetImagePath=''):
    return _legacy(sourceImagePath, targetImagePath, 'smooth')
