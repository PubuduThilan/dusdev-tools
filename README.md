# DuskDev Tools

DuskDev Tools is a Flask-based 3D modern file converter website with image conversion, image to PDF, FFmpeg-powered media tools, browser-side developer tools, and a donation/support section.

## Local setup

```bash
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Render Free deployment

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
gunicorn app:app
```

## Donation links

Set these Environment Variables in Render:

```bash
DONATION_BUY_ME_COFFEE_URL=https://www.buymeacoffee.com/yourname
DONATION_PAYPAL_URL=https://www.paypal.me/yourname
DONATION_KOFI_URL=https://ko-fi.com/yourname
```

## Media tools

Audio and video tools need FFmpeg. This project supports system FFmpeg and also includes `imageio-ffmpeg` as a fallback. Heavy media conversion is better on a VPS than free hosting.
