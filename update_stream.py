import subprocess
import sys

VIDEO_URL = "https://rutube.ru/video/private/3ccdc6ef20f8d93b76a3c11400680030/?p=jybZfNjs3FBcfKV-hZNqqQ"
OUTPUT_FILE = "stream.m3u8"


def get_fresh_url() -> str:
    cmd = ["yt-dlp", "--no-warnings", "-f", "b", "-g", VIDEO_URL]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("yt-dlp did not return a stream URL.")
    return lines[0]


def main() -> None:
    try:
        stream_url = get_fresh_url()
    except subprocess.CalledProcessError as exc:
        print("yt-dlp failed:", exc.stderr, file=sys.stderr)
        sys.exit(1)

    playlist = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:3\n"
        '#EXTINF:-1 group-title="Rutube",Rutube Video\n'
        f"{stream_url}\n"
    )

    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(playlist)

    print(f"Wrote {OUTPUT_FILE} successfully.")


if __name__ == "__main__":
    main()
