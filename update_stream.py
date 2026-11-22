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


def get_ytdlp_url() -> str:
    cmd = [
        "yt-dlp",
        "--no-warnings",
        "--user-agent",
        USER_AGENT,
        "--referer",
        VIDEO_URL,
        "-g",
        VIDEO_URL,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("yt-dlp did not return a stream URL.")
    return lines[0]


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


def build_master_playlist(manifest_text: str, base_url: str) -> str:
    raw_lines = [line.rstrip("\r\n") for line in manifest_text.splitlines()]
    has_extm3u = any(line.strip() == "#EXTM3U" for line in raw_lines)

    output_lines: list[str] = []
    if not has_extm3u:
        output_lines.append("#EXTM3U")

    has_version = False
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("#EXT-X-VERSION:"):
            output_lines.append("#EXT-X-VERSION:5")
            has_version = True
            continue

        if stripped == "#EXTM3U":
            output_lines.append("#EXTM3U")
            if not has_version:
                output_lines.append("#EXT-X-VERSION:5")
                has_version = True
            continue

        # Թարմացնում ենք URI="..." պարամետրերը (օրինակ՝ #EXT-X-MEDIA)
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

        # Հոսքի/սեգմենտի հղումները դարձնում ենք բացարձակ URL-ներ
        output_lines.append(urljoin(base_url, stripped))

    if "#EXT-X-INDEPENDENT-SEGMENTS" not in [l.strip() for l in output_lines]:
        output_lines.append("#EXT-X-INDEPENDENT-SEGMENTS")

    return "\n".join(output_lines) + "\n"


def main() -> None:
    try:
        stream_url = get_ytdlp_url()
    except subprocess.CalledProcessError as exc:
        print("yt-dlp failed:", exc.stderr, file=sys.stderr)
        sys.exit(1)

    referer = detect_referer(VIDEO_URL, stream_url)

    try:
        manifest_text = fetch_text(stream_url, referer=referer)
        playlist = build_master_playlist(manifest_text, base_url=stream_url)
    except Exception as exc:
        print(f"Manifest fetch failed ({exc}), writing fallback playlist.", file=sys.stderr)
        playlist = (
            "#EXTM3U\n"
            "#EXT-X-VERSION:5\n"
            f'#EXT-X-STREAM-INF:BANDWIDTH=2000000,NAME="OK Live"\n'
            f"{stream_url}\n"
            "#EXT-X-INDEPENDENT-SEGMENTS\n"
        )

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(playlist)

    print(f"Wrote {OUTPUT_FILE} successfully.")


if __name__ == "__main__":
    main()
