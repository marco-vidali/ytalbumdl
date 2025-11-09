import os
import requests
from io import BytesIO
from PIL import Image
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TRCK, TDRC
import yt_dlp

# ---------------- CONFIG ----------------
DOWNLOADS_FOLDER = "Downloads"
# Assicurati di avere il cookies.txt esportato da YouTube nello stesso folder dello script
COOKIES_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), "cookies.txt")
# ---------------------------------------

def sanitize_filename(name):
    """Remove invalid characters from filenames."""
    if not name:
        return ''
    return "".join(c for c in name if c not in r'<>:"/\\|?*').strip()

def download_audio(video_url, output_path):
    """Download video as MP3 using cookies.txt."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'quiet': True,
        'cookiefile': COOKIES_FILE,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

def download_and_crop_thumbnail(thumbnails):
    """Download thumbnail, crop to square, and return image bytes."""
    url = thumbnails[-1]['url']  # highest resolution
    resp = requests.get(url, timeout=15)
    img = Image.open(BytesIO(resp.content)).convert("RGB")

    w, h = img.size
    min_dim = min(w, h)
    left = (w - min_dim) // 2
    top = (h - min_dim) // 2
    img_cropped = img.crop((left, top, left + min_dim, top + min_dim))

    buf = BytesIO()
    img_cropped.save(buf, format="JPEG")
    return buf.getvalue()

def embed_cover(mp3_path, img_bytes, title, track_num, artist, album, year):
    """Embed cover image and metadata tags."""
    audio = MP3(mp3_path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TRCK(encoding=3, text=str(track_num)))
    audio.tags.add(TPE1(encoding=3, text=artist))
    audio.tags.add(TALB(encoding=3, text=album))
    audio.tags.add(TDRC(encoding=3, text=str(year)))
    audio.tags.add(APIC(
        encoding=3,
        mime='image/jpeg',
        type=3,
        desc='Cover',
        data=img_bytes
    ))
    audio.save()

def main():
    playlist_url = input("Enter YouTube playlist/album URL: ").strip()
    os.makedirs(DOWNLOADS_FOLDER, exist_ok=True)

    # Extract playlist info
    ydl_opts = {'quiet': True, 'extract_flat': True, 'cookiefile': COOKIES_FILE}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        playlist_info = ydl.extract_info(playlist_url, download=False)

    album_title = sanitize_filename(playlist_info.get('title', 'Unknown Album'))
    album_folder = os.path.join(DOWNLOADS_FOLDER, album_title)
    os.makedirs(album_folder, exist_ok=True)

    default_artist = sanitize_filename(playlist_info.get('uploader', 'Unknown Artist'))
    artist_name = input(f"Enter artist name [{default_artist}]: ").strip() or default_artist

    upload_date = playlist_info.get('upload_date', '20250101')
    default_year = upload_date[:4]
    year = input(f"Enter year [{default_year}]: ").strip() or default_year

    if playlist_info.get('_type') == 'playlist':
        entries = playlist_info.get('entries', [])
    else:
        entries = [playlist_info]
    entries.sort(key=lambda x: x.get('playlist_index', 0))

    # Show tracks and ask for cover
    print("\nTracks:")
    for idx, entry in enumerate(entries, start=1):
        print(f"{idx}. {entry.get('title')}")

    cover_index = int(input("\nChoose track index to use as album cover: ")) - 1
    cover_track = entries[cover_index]

    # Download cover thumbnail
    with yt_dlp.YoutubeDL({'quiet': True, 'cookiefile': COOKIES_FILE}) as ydl:
        video_info = ydl.extract_info(cover_track['url'], download=False)
    thumbnails = video_info.get('thumbnails', [])
    album_cover_bytes = download_and_crop_thumbnail(thumbnails)

    # Download all tracks
    for idx, entry in enumerate(entries, start=1):
        song_title = sanitize_filename(entry.get('title', f"Track {idx}"))
        video_url = entry['url']

        filename = f"{idx:02d} - {song_title}.%(ext)s"
        output_path = os.path.join(album_folder, filename)

        print(f"\nDownloading: {song_title}")
        download_audio(video_url, output_path)

        mp3_path = os.path.join(album_folder, f"{idx:02d} - {song_title}.mp3")
        print(f"Embedding cover and tags: {song_title}")
        embed_cover(mp3_path, album_cover_bytes, song_title, idx, artist_name, album_title, year)

    print(f"\n✅ All songs downloaded in: '{album_folder}'")

if __name__ == "__main__":
    main()
