import json
import re
import subprocess
import sys
from urllib.parse import urljoin, urlparse
import urllib.request

VIDEO_URL = "https://ok.ru/live/664807546380"
OUTPUT_FILE = "stream.m3u8"

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


def get_ytdlp_info() -> dict:
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--user-agent",
        USER_AGENT,
        "--referer",
        VIDEO_URL,
        "-J",
        VIDEO_URL,
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


def build_master_from_formats(info: dict) -> str | None:
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

        fmt_note = fmt.get("format_note") or fmt.get("format_id") or "Stream"
        safe_name = str(fmt_note).replace('"', "")

        attrs = f"BANDWIDTH={bandwidth}{resolution_attr},NAME=\"{safe_name}\""
        hls_variants.append((bandwidth, attrs, url))

    if not hls_variants:
        return None

    # Դասավորում ենք ըստ bitrate-ի (փոքրից մեծ)
    hls_variants.sort(key=lambda item: item[0])

    lines: list[str] = ["#EXTM3U", "#EXT-X-VERSION:5"]
    for _, attrs, url in hls_variants:
        lines.append(f"#EXT-X-STREAM-INF:{attrs}")
        lines.append(url)

    lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
    return "\n".join(lines) + "\n"


def main() -> None:
    try:
        info = get_ytdlp_info()
    except subprocess.CalledProcessError as exc:
        print("yt-dlp failed:", exc.stderr, file=sys.stderr)
        sys.exit(1)

    playlist = build_master_from_formats(info)

    if not playlist:
        fallback_url = info.get("url") or ""
        if not fallback_url:
            print("No playable URL found in yt-dlp output.", file=sys.stderr)
            sys.exit(1)

        referer = detect_referer(VIDEO_URL, fallback_url)
        try:
            manifest_text = fetch_text(fallback_url, referer=referer)
            playlist = build_master_from_manifest(manifest_text, base_url=fallback_url)
        except Exception as exc:
            print(f"Manifest check failed ({exc}).", file=sys.stderr)
            playlist = None

        if not playlist:
            playlist = (
                "#EXTM3U\n"
                "#EXT-X-VERSION:5\n"
                '#EXT-X-STREAM-INF:BANDWIDTH=2000000,NAME="OK Live"\n'
                f"{fallback_url}\n"
                "#EXT-X-INDEPENDENT-SEGMENTS\n"
            )

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(playlist)

    print(f"Wrote {OUTPUT_FILE} successfully.")


if __name__ == "__main__":
    main()
