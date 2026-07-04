import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from PIL import Image, UnidentifiedImageError
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.utils import secure_filename


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
CONVERTED_DIR = BASE_DIR / "converted"
MAX_FILE_SIZE = 25 * 1024 * 1024
MAX_FILE_SIZE_MB = MAX_FILE_SIZE // (1024 * 1024)

IMAGE_CONVERSIONS = {
    "jpg_to_png": {
        "label": "JPG to PNG",
        "inputs": {"jpg", "jpeg"},
        "output": "png",
    },
    "png_to_jpg": {
        "label": "PNG to JPG",
        "inputs": {"png"},
        "output": "jpg",
    },
    "webp_to_png": {
        "label": "WEBP to PNG",
        "inputs": {"webp"},
        "output": "png",
    },
    "png_to_webp": {
        "label": "PNG to WEBP",
        "inputs": {"png"},
        "output": "webp",
    },
}

IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
PDF_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
MP4_EXTENSIONS = {"mp4"}
VIDEO_EXTENSIONS = {"mp4", "mov", "m4v", "webm"}
AUDIO_EXTENSIONS = {"mp3", "wav", "m4a", "aac", "ogg", "flac"}
AUDIO_OUTPUTS = {"mp3", "wav", "aac", "ogg"}

# Reject executable and script-like uploads, including double extensions.
DANGEROUS_EXTENSIONS = {
    "app",
    "bat",
    "bin",
    "cmd",
    "com",
    "cpl",
    "dll",
    "exe",
    "gadget",
    "hta",
    "jar",
    "js",
    "jse",
    "msi",
    "php",
    "ps1",
    "scr",
    "sh",
    "vb",
    "vbe",
    "wsf",
}


app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")


def ensure_directories():
    """Create local storage folders when the app starts."""
    UPLOAD_DIR.mkdir(exist_ok=True)
    CONVERTED_DIR.mkdir(exist_ok=True)


def cleanup_old_files(max_age_seconds=60 * 60):
    """Remove old uploads and converted files so free hosting disks stay tidy."""
    now = time.time()
    for folder in (UPLOAD_DIR, CONVERTED_DIR):
        if not folder.exists():
            continue
        for path in folder.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            if now - path.stat().st_mtime > max_age_seconds:
                safe_remove(path)


def safe_remove(path):
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def file_extension(filename):
    return Path(filename).suffix.lower().lstrip(".")


def has_dangerous_extension(filename):
    parts = Path(filename).name.lower().split(".")[1:]
    return any(part in DANGEROUS_EXTENSIONS for part in parts)


def validate_and_save_upload(file_storage, allowed_extensions):
    """Validate extension, size, and filename before saving an upload."""
    if not file_storage or not file_storage.filename:
        return None, None, "Please choose a file to upload."

    original_name = file_storage.filename
    cleaned_name = secure_filename(original_name)
    extension = file_extension(cleaned_name)

    if not cleaned_name or not extension:
        return None, None, "The uploaded file needs a valid filename and extension."

    if has_dangerous_extension(original_name):
        return None, None, "This file type is not allowed for security reasons."

    if extension not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        return None, None, f"Unsupported file type. Allowed types: {allowed}."

    stored_name = f"{uuid.uuid4().hex}_{cleaned_name}"
    upload_path = UPLOAD_DIR / stored_name
    file_storage.save(upload_path)

    if upload_path.stat().st_size > MAX_FILE_SIZE:
        safe_remove(upload_path)
        return None, None, f"Files must be {MAX_FILE_SIZE_MB}MB or smaller."

    return upload_path, extension, None


def unique_output_name(source_path, output_extension):
    source_stem = secure_filename(Path(source_path).stem)[:40] or "converted"
    return f"{source_stem}-{uuid.uuid4().hex[:12]}.{output_extension}"


def flatten_to_rgb(image):
    """Place transparent images on a white background for JPG/PDF output."""
    if image.mode in ("RGBA", "LA") or "transparency" in image.info:
        rgba_image = image.convert("RGBA")
        background = Image.new("RGB", rgba_image.size, (255, 255, 255))
        background.paste(rgba_image, mask=rgba_image.getchannel("A"))
        return background
    return image.convert("RGB")


def verify_image(path):
    with Image.open(path) as image:
        image.verify()


def ffmpeg_path():
    """Return a usable FFmpeg binary path.

    On VPS hosting, FFmpeg is usually installed as a system package.
    On some free Python hosts, imageio-ffmpeg can provide a bundled binary.
    """
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def run_ffmpeg(command):
    """Run FFmpeg safely without shell=True."""
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None


def ffmpeg_error_response():
    return (
        jsonify(
            {
                "error": (
                    "FFmpeg is not installed or is not available on this server. "
                    "Install FFmpeg, add it to PATH, or install imageio-ffmpeg."
                )
            }
        ),
        503,
    )


@app.before_request
def run_housekeeping():
    cleanup_old_files()


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.context_processor
def inject_globals():
    return {
        "current_year": time.strftime("%Y"),
        "max_upload_mb": MAX_FILE_SIZE_MB,
        "donation_links": {
            "buy_me_a_coffee": os.environ.get("DONATION_BUY_ME_COFFEE_URL", ""),
            "paypal": os.environ.get("DONATION_PAYPAL_URL", ""),
            "kofi": os.environ.get("DONATION_KOFI_URL", ""),
        },
    }


@app.errorhandler(RequestEntityTooLarge)
def handle_large_file(error):
    return jsonify({"error": f"Files must be {MAX_FILE_SIZE_MB}MB or smaller."}), 413


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/image-tools")
@app.route("/jpg-to-png-converter")
@app.route("/png-to-jpg-converter")
def image_tools():
    return render_template("image_tools.html", conversions=IMAGE_CONVERSIONS)


@app.route("/pdf-tools")
@app.route("/image-to-pdf-converter")
def pdf_tools():
    return render_template("pdf_tools.html")


@app.route("/audio-video-tools")
@app.route("/mp4-to-mp3-converter")
def audio_video_tools():
    ffmpeg_available = ffmpeg_path() is not None
    return render_template("audio_video_tools.html", ffmpeg_available=ffmpeg_available)


@app.route("/developer-tools")
def developer_tools():
    return render_template("developer_tools.html")


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@app.route("/support")
def support():
    return render_template("support.html")


@app.route("/api/convert-image", methods=["POST"])
def convert_image():
    conversion_key = request.form.get("conversion", "")
    conversion = IMAGE_CONVERSIONS.get(conversion_key)
    if not conversion:
        return jsonify({"error": "Please choose a supported image conversion."}), 400

    upload_path, extension, error = validate_and_save_upload(
        request.files.get("file"),
        IMAGE_EXTENSIONS,
    )
    if error:
        return jsonify({"error": error}), 400

    if extension not in conversion["inputs"]:
        safe_remove(upload_path)
        expected = ", ".join(sorted(conversion["inputs"]))
        return (
            jsonify({"error": f"{conversion['label']} requires a {expected} file."}),
            400,
        )

    output_extension = conversion["output"]
    output_name = unique_output_name(upload_path, output_extension)
    output_path = CONVERTED_DIR / output_name

    try:
        verify_image(upload_path)
        with Image.open(upload_path) as image:
            if output_extension == "jpg":
                image = flatten_to_rgb(image)
                image.save(output_path, "JPEG", quality=92, optimize=True)
            elif output_extension == "webp":
                image.save(output_path, "WEBP", quality=90, method=6)
            else:
                image.save(output_path, "PNG", optimize=True)
    except (UnidentifiedImageError, OSError):
        safe_remove(output_path)
        return jsonify({"error": "We could not read that image file."}), 400
    finally:
        safe_remove(upload_path)

    return jsonify(
        {
            "message": f"{conversion['label']} conversion complete.",
            "download_url": url_for("download_file", filename=output_name),
            "filename": output_name,
        }
    )


@app.route("/api/image-to-pdf", methods=["POST"])
def image_to_pdf():
    upload_path, extension, error = validate_and_save_upload(
        request.files.get("file"),
        PDF_IMAGE_EXTENSIONS,
    )
    if error:
        return jsonify({"error": error}), 400

    output_name = unique_output_name(upload_path, "pdf")
    output_path = CONVERTED_DIR / output_name

    try:
        verify_image(upload_path)
        with Image.open(upload_path) as image:
            flatten_to_rgb(image).save(output_path, "PDF", resolution=100.0)
    except (UnidentifiedImageError, OSError):
        safe_remove(output_path)
        return jsonify({"error": "We could not turn that image into a PDF."}), 400
    finally:
        safe_remove(upload_path)

    return jsonify(
        {
            "message": "Image to PDF conversion complete.",
            "download_url": url_for("download_file", filename=output_name),
            "filename": output_name,
        }
    )


@app.route("/api/mp4-to-mp3", methods=["POST"])
def mp4_to_mp3():
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return ffmpeg_error_response()

    upload_path, extension, error = validate_and_save_upload(
        request.files.get("file"),
        MP4_EXTENSIONS,
    )
    if error:
        return jsonify({"error": error}), 400

    output_name = unique_output_name(upload_path, "mp3")
    output_path = CONVERTED_DIR / output_name
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(upload_path),
        "-vn",
        "-codec:a",
        "libmp3lame",
        "-q:a",
        "2",
        str(output_path),
    ]

    result = run_ffmpeg(command)
    safe_remove(upload_path)

    if result is None:
        safe_remove(output_path)
        return jsonify({"error": "The conversion took too long. Try a smaller file."}), 504

    if result.returncode != 0 or not output_path.exists():
        safe_remove(output_path)
        return jsonify({"error": "FFmpeg could not convert this MP4 file."}), 400

    return jsonify(
        {
            "message": "MP4 to MP3 conversion complete.",
            "download_url": url_for("download_file", filename=output_name),
            "filename": output_name,
        }
    )


@app.route("/api/convert-audio", methods=["POST"])
def convert_audio():
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return ffmpeg_error_response()

    output_format = request.form.get("output_format", "mp3").lower()
    if output_format not in AUDIO_OUTPUTS:
        return jsonify({"error": "Please choose a supported output format."}), 400

    upload_path, extension, error = validate_and_save_upload(
        request.files.get("file"),
        AUDIO_EXTENSIONS,
    )
    if error:
        return jsonify({"error": error}), 400

    output_name = unique_output_name(upload_path, output_format)
    output_path = CONVERTED_DIR / output_name
    codec_args = {
        "mp3": ["-codec:a", "libmp3lame", "-q:a", "2"],
        "wav": ["-codec:a", "pcm_s16le"],
        "aac": ["-codec:a", "aac", "-b:a", "192k"],
        "ogg": ["-codec:a", "libvorbis", "-q:a", "5"],
    }[output_format]

    command = [ffmpeg, "-y", "-i", str(upload_path), "-vn", *codec_args, str(output_path)]

    result = run_ffmpeg(command)
    safe_remove(upload_path)

    if result is None:
        safe_remove(output_path)
        return jsonify({"error": "The conversion took too long. Try a smaller file."}), 504

    if result.returncode != 0 or not output_path.exists():
        safe_remove(output_path)
        return jsonify({"error": "FFmpeg could not convert this audio file."}), 400

    return jsonify(
        {
            "message": f"Audio conversion to {output_format.upper()} complete.",
            "download_url": url_for("download_file", filename=output_name),
            "filename": output_name,
        }
    )


@app.route("/api/video-to-gif", methods=["POST"])
def video_to_gif():
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return ffmpeg_error_response()

    upload_path, extension, error = validate_and_save_upload(
        request.files.get("file"),
        VIDEO_EXTENSIONS,
    )
    if error:
        return jsonify({"error": error}), 400

    output_name = unique_output_name(upload_path, "gif")
    output_path = CONVERTED_DIR / output_name
    command = [
        ffmpeg,
        "-y",
        "-t",
        "12",
        "-i",
        str(upload_path),
        "-vf",
        "fps=12,scale=480:-1:flags=lanczos",
        str(output_path),
    ]

    result = run_ffmpeg(command)
    safe_remove(upload_path)

    if result is None:
        safe_remove(output_path)
        return jsonify({"error": "GIF creation took too long. Try a shorter video."}), 504

    if result.returncode != 0 or not output_path.exists():
        safe_remove(output_path)
        return jsonify({"error": "FFmpeg could not create a GIF from this video."}), 400

    return jsonify(
        {
            "message": "Video to GIF conversion complete.",
            "download_url": url_for("download_file", filename=output_name),
            "filename": output_name,
        }
    )


@app.route("/api/compress-video", methods=["POST"])
def compress_video():
    ffmpeg = ffmpeg_path()
    if not ffmpeg:
        return ffmpeg_error_response()

    upload_path, extension, error = validate_and_save_upload(
        request.files.get("file"),
        VIDEO_EXTENSIONS,
    )
    if error:
        return jsonify({"error": error}), 400

    output_name = unique_output_name(upload_path, "mp4")
    output_path = CONVERTED_DIR / output_name
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(upload_path),
        "-vcodec",
        "libx264",
        "-crf",
        "28",
        "-preset",
        "fast",
        "-acodec",
        "aac",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    result = run_ffmpeg(command)
    safe_remove(upload_path)

    if result is None:
        safe_remove(output_path)
        return jsonify({"error": "Compression took too long. Try a smaller file."}), 504

    if result.returncode != 0 or not output_path.exists():
        safe_remove(output_path)
        return jsonify({"error": "FFmpeg could not compress this video."}), 400

    return jsonify(
        {
            "message": "Video compression complete.",
            "download_url": url_for("download_file", filename=output_name),
            "filename": output_name,
        }
    )


@app.route("/download/<path:filename>")
def download_file(filename):
    safe_name = secure_filename(filename)
    if not safe_name or safe_name != filename:
        abort(404)
    return send_from_directory(CONVERTED_DIR, safe_name, as_attachment=True)


ensure_directories()

@app.route("/sitemap.xml")
def sitemap():
    pages = [
        {"loc": url_for("index", _external=True), "changefreq": "weekly", "priority": "1.0"},
    {"loc": url_for("image_tools", _external=True), "changefreq": "weekly", "priority": "0.9"},
    {"loc": url_for("pdf_tools", _external=True), "changefreq": "weekly", "priority": "0.9"},
    {"loc": url_for("audio_video_tools", _external=True), "changefreq": "weekly", "priority": "0.9"},
    {"loc": url_for("developer_tools", _external=True), "changefreq": "weekly", "priority": "0.8"},
    {"loc": url_for("about", _external=True), "changefreq": "monthly", "priority": "0.6"},
    {"loc": url_for("privacy", _external=True), "changefreq": "yearly", "priority": "0.4"},
    {"loc": url_for("terms", _external=True), "changefreq": "yearly", "priority": "0.4"},
    {"loc": url_for("contact", _external=True), "changefreq": "monthly", "priority": "0.5"},
    {"loc": url_for("support", _external=True), "changefreq": "monthly", "priority": "0.5"},

    {"loc": "https://duskdevtools.store/jpg-to-png-converter", "changefreq": "weekly", "priority": "0.8"},
    {"loc": "https://duskdevtools.store/png-to-jpg-converter", "changefreq": "weekly", "priority": "0.8"},
    {"loc": "https://duskdevtools.store/image-to-pdf-converter", "changefreq": "weekly", "priority": "0.8"},
    {"loc": "https://duskdevtools.store/mp4-to-mp3-converter", "changefreq": "weekly", "priority": "0.8"},
    ]

    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append(
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    )

    for page in pages:
        xml.append(
            f"""
            <url>
                <loc>{page["loc"]}</loc>
                <changefreq>{page["changefreq"]}</changefreq>
                <priority>{page["priority"]}</priority>
            </url>
            """
        )

    xml.append("</urlset>")

    return Response(
        "\n".join(xml),
        mimetype="application/xml"
    )


@app.route("/robots.txt")
def robots():
    content = """User-agent: *
Allow: /

Sitemap: https://duskdevtools.store/sitemap.xml
"""

    return Response(
        content,
        mimetype="text/plain"
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
