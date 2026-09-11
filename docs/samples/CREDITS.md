# The field collection

Five starting points for the editor: fur, feathers of light, fine botanical detail, and wide-open landscapes. All sample files are bundled locally; the app and site do not fetch them from a photo service at runtime.

| File | Creator / source | Reuse terms | A good place to start |
|---|---|---|---|
| [cheerful-puppy.png](cheerful-puppy.png) | Generated for this project at the owner's request | [Generation provenance and prompt](GENERATED.md) | Faded film, foreground cutout |
| [fox.jpg](fox.jpg) | [Ray Hennessy / Unsplash](https://unsplash.com/photos/fox-laying-on-snow-qQUtvVdurHg) | [Unsplash License](https://unsplash.com/license) | Warm sepia, silver monochrome |
| [alpine-lake.jpg](alpine-lake.jpg) | [Nunzio Guerrera / Unsplash](https://unsplash.com/photos/a-mountain-range-is-reflected-in-the-still-water-of-a-lake-37XGaPVDTEg) | [Unsplash License](https://unsplash.com/license) | Ink & sand, auto contrast |
| [fern.jpg](fern.jpg) | [Ian Dziuk / Unsplash](https://unsplash.com/photos/green-fern-plant-in-close-up-photography-KPfSQdeptbs) | [Unsplash License](https://unsplash.com/license) | Edge recognition, color segmentation |
| [butterfly.jpg](butterfly.jpg) | [Ivan Jevtic / Unsplash](https://unsplash.com/photos/shallow-focus-photography-of-butterfly-on-flowers-7vjonHYnDco) | [Unsplash License](https://unsplash.com/license) | Soft vignette, faded film |

The four Unsplash photographs are downloaded as JPEGs with a maximum width of 1,600 pixels for a lightweight showcase. Their photographers retain ownership; they are not covered by a software license. The puppy is AI-generated, not a real photograph. Effect previews are transformations of these samples.

`python tools/fetch_samples.py` refreshes the four Unsplash downloads and verifies that each response decodes as an image. No API key is needed. Regenerating the puppy is separate; its exact prompt is recorded in `GENERATED.md`.
