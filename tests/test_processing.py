from pathlib import Path
import pytest
from PIL import Image, ImageFilter
import image_processing as ip


@pytest.fixture
def photo():
    image = Image.new('RGB', (8, 6))
    image.putdata([(x * 29, y * 41, (x * 19 + y * 31) % 256) for y in range(6) for x in range(8)])
    return image


@pytest.mark.parametrize('effect', [e.key for e in ip.EFFECTS if e.key != 'cutout'])
@pytest.mark.parametrize('mode,size', [('RGB', (8, 6)), ('RGBA', (7, 5)), ('L', (1, 1)), ('P', (3, 3))])
def test_all_effects_keep_input_and_accept_modes(effect, mode, size):
    source = Image.new(mode, size)
    before = source.tobytes()
    result = ip.apply_effect(source, effect)
    assert source.tobytes() == before
    assert result.size == (tuple(max(1, n // 2) for n in size) if effect == 'resize' else size)


def test_rotation_mirror_are_pixel_exact(photo):
    rotated = ip.apply_effect(photo, 'rotate')
    mirrored = ip.apply_effect(photo, 'mirror')
    for y in range(photo.height):
        for x in range(photo.width):
            assert rotated.getpixel((x, y)) == photo.getpixel((photo.width - 1 - x, photo.height - 1 - y))
            assert mirrored.getpixel((x, y)) == photo.getpixel((photo.width - 1 - x, y))


def test_resize_averages_instead_of_overflowing():
    result = ip.apply_effect(Image.new('RGB', (4, 4), (80, 80, 80)), 'resize')
    assert result.size == (2, 2)
    assert set(result.get_flattened_data()) == {80}


def test_edges_match_legacy_neighbor_rule(photo):
    gray = photo.convert('L')
    result = ip.apply_effect(photo, 'edge', 20)
    for y in range(photo.height):
        for x in range(photo.width):
            expected = 0
            if x < photo.width - 1 and y > 0:
                v = gray.getpixel((x, y))
                expected = 255 if (abs(v - gray.getpixel((x + 1, y))) > 20 or abs(v - gray.getpixel((x, y - 1))) > 20) else 0
            assert result.getpixel((x, y)) == expected


@pytest.mark.parametrize('threshold', [0, 200, -1, '40', 2.4, True])
def test_threshold_validation(threshold, photo):
    with pytest.raises(ValueError):
        ip.apply_effect(photo, 'edge', threshold)


def test_primary_threshold():
    source = Image.new('RGB', (1, 1), (127, 128, 255))
    assert ip.apply_effect(source, 'primary').getpixel((0, 0)) == (0, 255, 255)


@pytest.mark.parametrize('tone,pattern', [(0, [0, 0, 0, 0]), (60, [0, 0, 255, 0]),
                                        (120, [255, 0, 0, 255]), (180, [255, 255, 0, 255]),
                                        (250, [255, 255, 255, 255])])
def test_halftone_patterns(tone, pattern):
    result = ip.apply_effect(Image.new('RGB', (2, 2), (tone,) * 3), 'halftone')
    assert [p[0] for p in result.get_flattened_data()] == pattern


@pytest.mark.parametrize('key,filter_', [('blur', ImageFilter.GaussianBlur(20)),
    ('minimum', ImageFilter.MinFilter(7)), ('sharpen', ImageFilter.UnsharpMask()),
    ('contour', ImageFilter.CONTOUR), ('detail', ImageFilter.DETAIL),
    ('enhance', ImageFilter.EDGE_ENHANCE_MORE), ('emboss', ImageFilter.EMBOSS),
    ('smooth', ImageFilter.Kernel((3, 3), [1, 2, 1, 2, 4, 2, 1, 2, 1], 16))])
def test_original_filter_parameters(photo, key, filter_):
    assert ip.apply_effect(photo, key).tobytes() == photo.filter(filter_).tobytes()


def test_transparency_survives_filter_and_png_export(tmp_path):
    image = Image.new('RGBA', (4, 4), (40, 60, 80, 75))
    result = ip.apply_effect(image, 'blur')
    assert result.getchannel('A').tobytes() == image.getchannel('A').tobytes()
    ip.save_image(result, tmp_path / 'transparent.png')
    assert ip.read_image(tmp_path / 'transparent.png').getpixel((0, 0))[3] == 75


def test_exif_orientation_and_palette_transparency(tmp_path):
    source = Image.new('RGB', (4, 2))
    exif = Image.Exif()
    exif[274] = 6
    source.save(tmp_path / 'phone.jpg', exif=exif)
    assert ip.read_image(tmp_path / 'phone.jpg').size == (2, 4)
    palette = Image.new('P', (2, 2))
    palette.save(tmp_path / 'palette.png', transparency=0)
    assert ip.read_image(tmp_path / 'palette.png').getpixel((0, 0))[3] == 0


@pytest.mark.parametrize('extension', sorted(ip.SUPPORTED_EXTENSIONS))
def test_export_formats(tmp_path, extension):
    target = tmp_path / f'output{extension}'
    ip.save_image(Image.new('RGBA', (8, 8), (30, 60, 90, 128)), target)
    with Image.open(target) as result:
        assert result.size == (8, 8)


def test_batch_preserves_originals_and_existing_exports_and_continues(tmp_path, photo):
    source = tmp_path / 'original.JPG'
    photo.save(source)
    original_bytes = source.read_bytes()
    occupied = tmp_path / 'original_processed.jpg'
    occupied.write_bytes(b'keep me')
    broken = tmp_path / 'broken.png'
    broken.write_bytes(b'not an image')
    progress = []
    report = ip.export_batch([source, source, broken], tmp_path, 'mirror', progress=lambda a, b: progress.append((a, b)))
    assert [p.name for p in report.saved] == ['original_processed_2.jpg']
    assert len(report.errors) == 1
    assert source.read_bytes() == original_bytes
    assert occupied.read_bytes() == b'keep me'
    assert progress == [(1, 2), (2, 2)]


def test_legacy_api_preview_and_save(photo, tmp_path):
    source = tmp_path / 'in.png'
    photo.save(source)
    preview = ip.rotatePicture(source, '')
    target = tmp_path / 'out.png'
    assert ip.rotatePicture(source, target) is None
    assert preview.tobytes() == ip.read_image(target).tobytes()


def test_folder_listing_and_invalid_destinations(tmp_path):
    (tmp_path / 'z.PNG').touch()
    (tmp_path / 'a.JPEG').touch()
    (tmp_path / 'notes.txt').touch()
    (tmp_path / 'directory.png').mkdir()
    assert [p.name for p in ip.list_images(tmp_path)] == ['a.JPEG', 'z.PNG']
    with pytest.raises(ValueError):
        ip.export_batch([], tmp_path / 'absent', 'mirror')


def test_color_segmentation_reduces_palette(photo):
    result = ip.apply_effect(photo, 'segments')
    assert len(set(result.get_flattened_data())) <= 6


def test_cutout_has_transparency_and_keeps_subject(tmp_path):
    from PIL import ImageDraw
    source = Image.new('RGB', (100, 100), '#eeeeee')
    ImageDraw.Draw(source).ellipse((25, 20, 75, 85), fill='#623a22')
    output = ip.apply_effect(source, 'cutout', roi=(.1, .1, .9, .95))
    assert output.mode == 'RGBA'
    assert output.getpixel((50, 50))[3] == 255
    assert output.getpixel((0, 0))[3] == 0
    path = tmp_path / 'subject.jpg'
    source.save(path)
    report = ip.export_batch([path], tmp_path, 'cutout', roi=(.1, .1, .9, .95))
    assert len(report.saved) == 1
    assert report.saved[0].suffix == '.png'
    assert ip.read_image(report.saved[0]).mode == 'RGBA'


def test_cutout_rejects_tiny_and_invalid_regions(photo):
    with pytest.raises(ValueError):
        ip.apply_effect(photo, 'cutout')
    with pytest.raises(ValueError):
        ip.apply_effect(Image.new('RGB', (20, 20)), 'cutout', roi=(.8, .8, .1, .1))


def test_partial_export_is_removed_on_encoder_error(tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError('encoder unavailable')
    monkeypatch.setattr(Image.Image, 'save', fail)
    target = tmp_path / 'partial.png'
    with pytest.raises(OSError):
        ip.save_image(Image.new('RGB', (2, 2)), target, exclusive=True)
    assert not target.exists()
