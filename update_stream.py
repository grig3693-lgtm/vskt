import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import urljoin, urlparse
import urllib.request

# Փոխեք այս արժեքները ձեր ռեպոզիտորիայի տվյալներով (կամ փոխանցեք Environment Variable-ով)
REPO_OWNER = os.getenv("REPO_OWNER", "grig3693-lgtm")
REPO_NAME = os.getenv("REPO_NAME", "vskt")
BRANCH = os.getenv("GIT_BRANCH", "main")
PLAYLIST_FILE = "playlist.m3u"

# Դադար հարցումների միջև (վայրկյաններով), որպեսզի OK.ru-ն չսահմանափակի հարցումները
REQUEST_DELAY_SECONDS = 1.5

STREAMS = [
    {
        "name": "OK Live 1",
        "group": "OK Live",
        "url": "https://ok.ru/live/664807546380",
        "output": "stream1.m3u8",
    },
    # Ավելացրեք մյուս հղումները այս նույն ձևաչափով.
    # {
    #     "name": "OK Live 2",
    #     "group": "OK Live",
    #     "url": "https://ok.ru/live/8602647142043",
    #     "output": "stream2.m3u8",
    # },
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)


def detect_referer(video_url: str, stream_url: str) -> str:
    match = re.search(r"/mid/(\d+)", stream_url)
    if match:
        return f"https://ok.ru/live/{match.group(1)}"
    if "ok.ru" in video_url:
        return video_url
    parsed = urlparse(video_url)
    return f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else video_url


def resolve_channel_referer(video_url: str) -> str:
    match = re.search(r"/live/(\d+)", video_url)
    if match:
        return f"https://ok.ru/live/{match.group(1)}"
    if "ok.ru" in video_url:
        return video_url
    parsed = urlparse(video_url)
    return f"{parsed.scheme}://{parsed.netloc}/" if parsed.netloc else "https://ok.ru/"


def get_ytdlp_info(video_url: str) -> dict:
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--user-agent",
        USER_AGENT,
        "--referer",
        video_url,
        "-J",
        video_url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def fetch_text(url: str, referer: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": referer,
            "Origin": "https://ok.ru",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


def is_media_playlist(manifest_text: str) -> bool:
    return "#EXTINF:" in manifest_text or ".ts" in manifest_text


def build_master_from_manifest(manifest_text: str, base_url: str) -> str | None:
    if is_media_playlist(manifest_text):
        return None

    raw_lines = [line.rstrip("\r\n") for line in manifest_text.splitlines()]
    output_lines: list[str] = ["#EXTM3U", "#EXT-X-VERSION:5"]

    for line in raw_lines:
        stripped = line.strip()
        if not stripped or stripped in ("#EXTM3U", "#EXT-X-INDEPENDENT-SEGMENTS"):
            continue
        if stripped.startswith("#EXT-X-VERSION:"):
            continue
        if stripped.startswith("#") and 'URI="' in line:
            line = re.sub(
                r'URI="([^"]+)"',
                lambda m: f'URI="{urljoin(base_url, m.group(1))}"',
                line,
            )
            output_lines.append(line)
            continue
        if stripped.startswith("#"):
            output_lines.append(line)
            continue
        output_lines.append(urljoin(base_url, stripped))

    output_lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
    return "\n".join(output_lines) + "\n"


def build_master_from_formats(info: dict, stream_name: str) -> str | None:
    formats = info.get("formats") or []
    hls_variants: list[tuple[int, str, str]] = []
    seen_urls: set[str] = set()

    for fmt in formats:
        url = fmt.get("url")
        if not url or url in seen_urls:
            continue
        if ".ts" in url.split("?")[0]:
            continue

        protocol = (fmt.get("protocol") or "").lower()
        ext = (fmt.get("ext") or "").lower()
        if "m3u8" not in protocol and "m3u8" not in url and ext != "m3u8":
            continue

        seen_urls.add(url)

        tbr = fmt.get("tbr") or fmt.get("vbr") or 0
        bandwidth = int(float(tbr) * 1000) if tbr else 1000000

        width = fmt.get("width")
        height = fmt.get("height")
        resolution_attr = f",RESOLUTION={width}x{height}" if width and height else ""

        fmt_note = fmt.get("format_note") or fmt.get("format_id") or stream_name
        safe_name = str(fmt_note).replace('"', "")

        attrs = f'BANDWIDTH={bandwidth}{resolution_attr},NAME="{safe_name}"'
        hls_variants.append((bandwidth, attrs, url))

    if not hls_variants:
        return None

    hls_variants.sort(key=lambda item: item[0])

    lines: list[str] = ["#EXTM3U", "#EXT-X-VERSION:5"]
    for _, attrs, url in hls_variants:
        lines.append(f"#EXT-X-STREAM-INF:{attrs}")
        lines.append(url)

    lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
    return "\n".join(lines) + "\n"


def generate_stream_m3u8(video_url: str, stream_name: str, output_file: str) -> bool:
    try:
        info = get_ytdlp_info(video_url)
    except subprocess.CalledProcessError as exc:
        print(f"[{stream_name}] yt-dlp failed: {exc.stderr.strip()}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[{stream_name}] Error parsing yt-dlp info: {exc}", file=sys.stderr)
        return False

    playlist = build_master_from_formats(info, stream_name)

    if not playlist:
        fallback_url = info.get("url") or ""
        if not fallback_url:
            print(f"[{stream_name}] No playable URL found.", file=sys.stderr)
            return False

        referer = detect_referer(video_url, fallback_url)
        try:
            manifest_text = fetch_text(fallback_url, referer=referer)
            playlist = build_master_from_manifest(manifest_text, base_url=fallback_url)
        except Exception as exc:
            print(f"[{stream_name}] Manifest check failed ({exc}).", file=sys.stderr)
            playlist = None

        if not playlist:
            playlist = (
                "#EXTM3U\n"
                "#EXT-X-VERSION:5\n"
                f'#EXT-X-STREAM-INF:BANDWIDTH=2000000,NAME="{stream_name}"\n'
                f"{fallback_url}\n"
                "#EXT-X-INDEPENDENT-SEGMENTS\n"
            )

    with open(output_file, "w", encoding="utf-8", newline="\n") as f:
        f.write(playlist)

    print(f"[{stream_name}] Wrote {output_file} successfully.")
    return True


def build_combined_playlist(generated_entries: list[dict]) -> str:
    lines: list[str] = ["#EXTM3U"]
    for item in generated_entries:
        name = item["name"]
        group = item.get("group") or "OK Live"
        filename = item["output"]
        referer = item.get("referer") or "https://ok.ru/"
        raw_url = (
            f"https://raw.githubusercontent.com/{REPO_OWNER}/{REPO_NAME}"
            f"/refs/heads/{BRANCH}/{filename}"
        )

        lines.append(f'#EXTINF:-1 group-title="{group}",{name}')
        lines.append(f"#EXTVLCOPT:http-user-agent={USER_AGENT}")
        lines.append(f"#EXTVLCOPT:http-referrer={referer}")
        lines.append(raw_url)
    return "\n".join(lines) + "\n"


def main() -> None:
    if not STREAMS:
        print("STREAMS list is empty.", file=sys.stderr)
        sys.exit(1)

    successful_entries: list[dict] = []

    for index, stream in enumerate(STREAMS):
        name = stream.get("name") or f"Stream {index + 1}"
        group = stream.get("group") or "OK Live"
        url = stream.get("url") or ""
        output_file = stream.get("output") or f"stream{index + 1}.m3u8"

        if not url:
            print(f"[{name}] Missing URL, skipping.", file=sys.stderr)
            continue

        ok = generate_stream_m3u8(url, name, output_file)
        if ok:
            successful_entries.append(
                {
                    "name": name,
                    "group": group,
                    "output": output_file,
                    "referer": resolve_channel_referer(url),
                }
            )

        if index < len(STREAMS) - 1 and REQUEST_DELAY_SECONDS > 0:
            time.sleep(REQUEST_DELAY_SECONDS)

    if not successful_entries:
        print("No stream playlists were generated.", file=sys.stderr)
        sys.exit(1)

    combined_content = build_combined_playlist(successful_entries)
    with open(PLAYLIST_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(combined_content)

    print(f"Wrote {PLAYLIST_FILE} with {len(successful_entries)} stream(s).")


if __name__ == "__main__":
    main()
