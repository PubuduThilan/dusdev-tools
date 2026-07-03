import unittest
from io import BytesIO

from PIL import Image

import app as duskdev


class DuskDevToolsSmokeTest(unittest.TestCase):
    def setUp(self):
        self.client = duskdev.app.test_client()

    def test_pages_render(self):
        pages = [
            "/",
            "/image-tools",
            "/pdf-tools",
            "/audio-video-tools",
            "/developer-tools",
            "/support",
            "/about",
            "/privacy",
            "/terms",
            "/contact",
            "/jpg-to-png-converter",
            "/image-to-pdf-converter",
            "/mp4-to-mp3-converter",
        ]
        for page in pages:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(page).status_code, 200)

    def test_png_to_jpg_conversion(self):
        source = BytesIO()
        Image.new("RGBA", (24, 16), (20, 120, 90, 160)).save(source, format="PNG")
        source.seek(0)

        response = self.client.post(
            "/api/convert-image",
            data={"conversion": "png_to_jpg", "file": (source, "sample.png")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        output_name = response.get_json()["filename"]
        download = self.client.get("/download/" + output_name)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, "image/jpeg")
        download.close()
        duskdev.safe_remove(duskdev.CONVERTED_DIR / output_name)

    def test_image_to_pdf_conversion(self):
        source = BytesIO()
        Image.new("RGB", (20, 20), (240, 180, 50)).save(source, format="JPEG")
        source.seek(0)

        response = self.client.post(
            "/api/image-to-pdf",
            data={"file": (source, "scan.jpg")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        output_name = response.get_json()["filename"]
        download = self.client.get("/download/" + output_name)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.mimetype, "application/pdf")
        download.close()
        duskdev.safe_remove(duskdev.CONVERTED_DIR / output_name)


if __name__ == "__main__":
    unittest.main()
