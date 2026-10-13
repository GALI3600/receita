import pytest

from app.errors import ErrorCode, InvalidUrlError
from app.services.youtube import extract_youtube_id

VIDEO_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    "url",
    [
        f"https://www.youtube.com/watch?v={VIDEO_ID}",
        f"http://www.youtube.com/watch?v={VIDEO_ID}",
        f"https://youtube.com/watch?v={VIDEO_ID}",
        f"www.youtube.com/watch?v={VIDEO_ID}",
        f"youtube.com/watch?v={VIDEO_ID}",
        f"https://m.youtube.com/watch?v={VIDEO_ID}",
        f"https://music.youtube.com/watch?v={VIDEO_ID}&feature=share",
        f"https://WWW.YouTube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&t=42s",
        f"https://www.youtube.com/watch?feature=youtu.be&v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&list=PLabc123&index=3",
        f"https://www.youtube.com/watch?v={VIDEO_ID}#t=30",
        f"https://www.youtube.com/watch/?v={VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}",
        f"https://youtu.be/{VIDEO_ID}?si=AbCdEf123&t=10",
        f"youtu.be/{VIDEO_ID}",
        f"https://www.youtube.com/shorts/{VIDEO_ID}",
        f"https://youtube.com/shorts/{VIDEO_ID}?feature=share",
        f"https://www.youtube.com/shorts/{VIDEO_ID}/",
        f"https://www.youtube.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/embed/{VIDEO_ID}?start=5&autoplay=1",
        f"https://www.youtube-nocookie.com/embed/{VIDEO_ID}",
        f"https://www.youtube.com/v/{VIDEO_ID}",
        f"https://www.youtube.com/live/{VIDEO_ID}?si=x",
        f"https://www.youtube.com:443/watch?v={VIDEO_ID}",
        f"  https://www.youtube.com/watch?v={VIDEO_ID}  \n",
    ],
)
def test_extract_youtube_id_accepts_video_links(url: str) -> None:
    assert extract_youtube_id(url) == VIDEO_ID


def test_extract_youtube_id_keeps_dash_and_underscore() -> None:
    assert extract_youtube_id("https://youtu.be/-pRC-FQXLE_") == "-pRC-FQXLE_"


@pytest.mark.parametrize(
    "url",
    [
        "",
        "   ",
        "receita de bolo",
        VIDEO_ID,
        "https://www.youtube.com/",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/watch?v=curto",
        f"https://www.youtube.com/watch?v={VIDEO_ID}x",
        f"https://www.youtube.com/watch?v={VIDEO_ID}&v=aaaaaaaaaaa",
        "https://www.youtube.com/playlist?list=PLabc123",
        "https://www.youtube.com/embed/videoseries?list=PLxyz123",
        "https://www.youtube-nocookie.com/embed/videoseries?list=PLxyz123",
        "https://www.youtube.com/v/videoseries?list=PLxyz123",
        "https://www.youtube.com/@RitaLobo",
        "https://www.youtube.com/channel/UC1234567890",
        "https://www.youtube.com/c/Panelinha",
        "https://www.youtube.com/user/panelinha",
        "https://www.youtube.com/results?search_query=bolo",
        f"https://www.youtube.com/shorts/{VIDEO_ID}/extra",
        f"https://youtu.be/{VIDEO_ID}/extra",
        "https://youtu.be/",
        f"https://youtube.com.evil.com/watch?v={VIDEO_ID}",
        f"https://evilyoutube.com/watch?v={VIDEO_ID}",
        f"https://youtu.be.evil.com/{VIDEO_ID}",
        f"https://www.youtube.com@evil.com/watch?v={VIDEO_ID}",
        f"https://user:pass@www.youtube.com/watch?v={VIDEO_ID}",
        f"https://vimeo.com/watch?v={VIDEO_ID}",
        f"ftp://www.youtube.com/watch?v={VIDEO_ID}",
        f"javascript:alert(1)//youtube.com/watch?v={VIDEO_ID}",
        f"https://www.youtube.com/watch?v={VIDEO_ID} https://youtu.be/{VIDEO_ID}",
        "https://www.youtube.com/watch?v=dQw4w9WgXc!",
    ],
)
def test_extract_youtube_id_rejects_non_video_links(url: str) -> None:
    with pytest.raises(InvalidUrlError) as exc_info:
        extract_youtube_id(url)
    assert exc_info.value.code == ErrorCode.INVALID_URL
    assert "YouTube" in exc_info.value.message
