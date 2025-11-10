import os
import requests
from io import BytesIO
from PIL import Image
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TRCK, TDRC
import yt_dlp

# ---------------- CONFIG ----------------
DOWNLOADS_FOLDER = "Downloads"
COOKIES_FILE = os.path.join(os.path.abspath(os.path.dirname(__file__)), "cookies.txt")
# ---------------------------------------

def sanitize_filename(name):
    # Per i file: sostituisce / con - ma mantiene tutto il resto
    if not name:
        return ''
    name = name.replace('/', ' - ')
    return "".join(c for c in name if c not in r'<>:"\\|?*').strip()

def download_audio(video_url, output_path):
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
    url = thumbnails[-1]['url']
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

def download_image_from_url(url):
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
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)
    except Exception:
        print("Warning: unable to load cookies, continuing without them.")
        with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
            playlist_info = ydl.extract_info(playlist_url, download=False)

    default_album = playlist_info.get('title', 'Unknown Album')
    print(f"\nDetected album title: {default_album}")
    album_title = input("Enter album title (or press Enter to keep it): ").strip() or default_album
    album_folder = os.path.join(DOWNLOADS_FOLDER, sanitize_filename(album_title))
    os.makedirs(album_folder, exist_ok=True)

    default_artist = playlist_info.get('uploader', 'Unknown Artist')
    artist_name = input(f"Enter artist name [{default_artist}]: ").strip() or default_artist

    upload_date = playlist_info.get('upload_date', '20250101')
    default_year = upload_date[:4]
    year = input(f"Enter year [{default_year}]: ").strip() or default_year

    entries = playlist_info.get('entries', [])
    entries.sort(key=lambda x: x.get('playlist_index', 0))
    song_titles = [entry.get('title', f"Track {idx+1}") for idx, entry in enumerate(entries)]

    # Rinominare canzoni manualmente
    while True:
        print("\nCurrent song titles:")
        for idx, title in enumerate(song_titles, start=1):
            print(f"{idx}. {title}")
        rename = input("Do you want to rename any song? (y/n): ").strip().lower()
        if rename != 'y':
            break
        track_num = int(input("Enter track number to rename: ").strip())
        if 1 <= track_num <= len(song_titles):
            new_title = input("Enter new title: ").strip()
            song_titles[track_num-1] = new_title
        else:
            print("Invalid track number.")

    # Scelta copertina
    print("\nCover options:")
    print("1. Use thumbnail from one of the playlist videos")
    print("2. Use image from a URL")
    cover_choice = input("Choose cover option (1/2): ").strip()

    if cover_choice == '1':
        cover_index = int(input("\nChoose track index to use as album cover: ")) - 1
        cover_track = entries[cover_index]
        with yt_dlp.YoutubeDL({'quiet': True, 'cookiefile': COOKIES_FILE}) as ydl:
            video_info = ydl.extract_info(cover_track['url'], download=False)
        thumbnails = video_info.get('thumbnails', [])
        album_cover_bytes = download_and_crop_thumbnail(thumbnails)
    elif cover_choice == '2':
        img_url = input("Enter image URL: ").strip()
        album_cover_bytes = download_image_from_url(img_url)
    else:
        print("Invalid choice. Using first track thumbnail by default.")
        cover_track = entries[0]
        with yt_dlp.YoutubeDL({'quiet': True, 'cookiefile': COOKIES_FILE}) as ydl:
            video_info = ydl.extract_info(cover_track['url'], download=False)
        thumbnails = video_info.get('thumbnails', [])
        album_cover_bytes = download_and_crop_thumbnail(thumbnails)

    # Download e tagging
    for idx, entry in enumerate(entries, start=1):
        display_title = song_titles[idx-1]
        file_title = sanitize_filename(display_title)
        video_url = entry['url']
        filename = f"{idx:02d} - {file_title}.%(ext)s"
        output_path = os.path.join(album_folder, filename)

        print(f"\nDownloading: {display_title}")
        try:
            download_audio(video_url, output_path)
        except Exception as e:
            print(f"Retrying without cookies... ({e})")
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': output_path,
                'quiet': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

        mp3_path = os.path.join(album_folder, f"{idx:02d} - {file_title}.mp3")
        print(f"Embedding cover and tags: {display_title}")
        embed_cover(mp3_path, album_cover_bytes, display_title, idx, artist_name, album_title, year)

    print(f"\n✅ All songs downloaded in: '{album_folder}'")

if __name__ == "__main__":
    main()
