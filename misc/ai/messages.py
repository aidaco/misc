import re
import base64
from typing import Self, Literal, ClassVar
from dataclasses import dataclass
import textwrap
from pathlib import Path

from rich.console import Group
from rich.panel import Panel
import pytest
from twidge.widgets import Close, EditString, Framed


URL_REGEX = re.compile(
    r"""
    https?:\/\/                            # Protocol (http or https)
    (?:www\.)?                             # Optional subdomain (www.)
    [-a-zA-Z0-9@:%._\+~#=]{2,256}          # Domain name
    \.[a-z]{2,6}                           # Top-level domain (e.g., .com, .net, .org)
    \b                                     # Word boundary to ensure no partial matches
    (?:[-a-zA-Z0-9@:%_\+.~#?&\/\/=]*)      # Optional path and query parameters
""",
    re.VERBOSE,
)


PATH_REGEX = re.compile(
    r"""
    (?:                         # Non-capturing group for starting path variations
        (?:[A-Z]:\\|/)          # Windows drive letter or Linux/Mac root directory
        |                       # OR
        ~/                      # Home directory (Linux/Mac)
    )
    (?:                         # Non-capturing group for path components
        [^\n/\\:?*<>"|]+        # Any character except path separators and special characters
        (?:/|\\)                # Path separator (either slash or backslash)
    )*                          # Match any number of path components
    [^\n/\\:?*<>"|]+            # File name with any character except special characters
    (?:\.[^\n/\\:?*<>"|]*)?     # Optional file extension
""",
    re.VERBOSE,
)


@dataclass
class Content:
    text: str | None
    image_urls: list[str] | None

    @classmethod
    def parse(cls, content):
        match content:
            case str():
                return cls(content, None)
            case [*parts]:
                texts = []
                image_urls = []
                for p in parts:
                    match p:
                        case {'type': 'text', 'text': text}:
                            texts.append(text)
                        case {'type': 'image_url', 'image_url': {'url': url}}:
                            image_urls.append(url)
                text = '\n'.join(texts)
                return cls(text, image_urls)

    def asdict(self):
        if self.image_urls is None:
            return self.text
        return [
            {'type': 'text', 'text': self.text},
            *(
                {
                    'type': 'image_url',
                    'image_url': {'url': url}
                }
                for url in self.image_urls
            )
        ]

    def __rich__(self):
        if not self.image_urls:
            return self.text
        links = ' '.join(
            f'[link={url}]Image {i}[/link]'
            for i, url in enumerate(self.image_urls)
        )
        return Group(
            self.text,
            ' '.join(
                f'[link={url}]Image {i}[/link]'
                for i, url in
                enumerate(self.image_urls)
            )
        )
    

@dataclass
class Message:
    role: Literal['system', 'user', 'assistant']
    content: Content
    styles: ClassVar = {
        "system": "bright_blue italic on black",
        "user": "bright_red on black",
        "assistant": "bright_green on black",
        "border": "bright_black bold not italic on black",
        "editor_border": "bright_yellow on black",
    }

    @classmethod
    def compose(cls, role, message='') -> Self:
        text = Close(
            Framed(
                EditString(
                    message, text_style=cls.styles[role], cursor_line_style=cls.styles[role]
                ),
                title=role,
                title_align="left",
                style=cls.styles['editor_border'],
            )
        ).run()
        text, urls = _extract_image_urls(text)
        return cls(role, Content(text, urls))

    @classmethod
    def parse(cls, message) -> Self:
        role = _get_item_or_attr(message, "role", None)
        content = _get_item_or_attr(message, "content", None)
        return cls(role, Content.parse(content))

    def asdict(self):
        return {
            'role': self.role,
            'content': self.content.asdict(),
        }

    def __rich__(self):
        return Panel.fit(
            self.content,
            title=self.role,
            title_align="left",
            style=self.styles[self.role],
            border_style=self.styles['border'],
        )


def _extract_image_urls(text, url_pattern=URL_REGEX, path_pattern=PATH_REGEX):
    urls, no_urls = _extract_matches(url_pattern, text)
    paths, cleaned = _extract_matches(path_pattern, no_urls)
    if not urls and not paths:
        return text.strip(), None
    urls.extend(
        _base64url(p.open("rb"))
        for p in map(Path, paths)
        if p.exists()
    )
    return cleaned.strip(), urls


def _extract_matches(pattern, text):
    matches = []

    def append(match):
        matches.append(match.group(0))
        return ""

    return matches, pattern.sub(append, text)


def _base64url(file):
    data = base64.b64encode(file.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{data}"


def _get_item_or_attr(obj, name, default=None):
    try:
        return obj[name]
    except (KeyError, TypeError):
        try:
            return getattr(obj, name)
        except AttributeError:
            return default




@pytest.mark.parametrize(
    "url",
    textwrap.dedent(
        r"""
    https://en.wikipedia.org/wiki/Example.com
    https://www.example.com/
    https://en.wikipedia.org/wiki/Example.com
    https://writequit.org/denver-emacs/presentations/files/example.org.html
    https://www.example.com/
    https://writequit.org/denver-emacs/presentations/files/example.org.html
    https://learn.microsoft.com/en-us/dotnet/samples-and-tutorials/
    https://en.wikipedia.org/wiki/Example.com
    https://learn.microsoft.com/en-us/dotnet/samples-and-tutorials/
    https://www.danword.com/crossword/Egfor_example
    https://www.example.com/
    https://www.danword.com/crossword/Egfor_example
    https://study.com/academy/lesson/when-how-to-use-eg-in-a-sentence.html
    https://www.example.com/
    https://study.com/academy/lesson/when-how-to-use-eg-in-a-sentence.html
    https://www.scribbr.com/definitions/for-example-abbreviation/
    https://sentence.yourdictionary.com/fr
    https://www.scribbr.com/definitions/for-example-abbreviation/
    https://preply.com/en/question/example-ex-or-eg-41620
    https://sentence.yourdictionary.com/de
    https://preply.com/en/question/example-ex-or-eg-41620
    https://www.grammarly.com/blog/know-your-latin-i-e-vs-e-g/
    https://www.grammarly.com/blog/spelling-plurals-with-s-es/
    https://www.grammarly.com/blog/know-your-latin-i-e-vs-e-g/
    https://study.com/academy/lesson/when-how-to-use-eg-in-a-sentence.html
    https://www.exampleit.com/
    https://study.com/academy/lesson/when-how-to-use-eg-in-a-sentence.html
    https://www.enago.com/academy/when-to-use-e-g-and-i-e-while-writing-your-paper/
    https://sentence.yourdictionary.com/jp
    https://www.enago.com/academy/when-to-use-e-g-and-i-e-while-writing-your-paper/
    https://www.aje.com/arc/editing-tip-using-eg-and-ie/
    https://www.itechguides.com/what-is-cn-in-active-directory/
    https://www.aje.com/arc/editing-tip-using-eg-and-ie/
    https://study.com/academy/lesson/when-how-to-use-eg-in-a-sentence.html
    https://en.wikipedia.org/wiki/.ru
    https://study.com/academy/lesson/when-how-to-use-eg-in-a-sentence.html
"""
    )
    .strip()
    .splitlines(),
)
def test_url_regex(url):
    assert URL_REGEX.fullmatch(url)


@pytest.mark.parametrize(
    "path",
    textwrap.dedent(
        r"""
    C:\Program Files\Microsoft Office\Office16\WINWORD.EXE
    /Applications/Google Chrome.app
    ~/Documents/myResume.pdf
    C:\Users\Public\Documents\shared.txt
    /usr/local/bin/python3
    /home/username/Pictures/vacation.jpg
    C:\Windows\System32\ntoskrnl.exe
    /System/Library/CoreServices/Applications/Finder.app
    ~/Downloads/latest_software_update.dmg
    C:\Program Files (x86)\Adobe\Acrobat Reader DC\AcroRd32.exe
    /Library/Application Support/iMovie/Shared/iMovie Effects/iMovie Audio/Soundtrack Effects/Sound Effects.mov
    ~/Music/favorite_song.mp3
    C:\Users\username\AppData\Local\Temp~DFDC253C-F1AB-4709-A312-E4F242608B8D.tmp
    /Applications/Utilities/Terminal.app
    ~/Library/Preferences/com.apple.finder.plist
    C:\Windows\System32\drivers\etc\hosts
    /etc/passwd
    ~/Desktop/screenshot.png
    C:\Windows\Fonts\arial.ttf
    /Library/Fonts/Arial.ttc
    ~/Videos/latest_funny_cat_video.mp4
    C:\Users\username\AppData\Roaming\Microsoft\Windows\Internet Explorer\Quick Launch\Google Chrome.lnk
    /Library/LaunchAgents/com.apple.kextd.plist
    ~/Library/Caches/com.apple.Safari/Cache.db
    C:\Windows\Temp\WERTemp.dat
    """
    )
    .strip()
    .splitlines(),
)
def test_path_regex(path):
    assert PATH_REGEX.fullmatch(path)


def test_extract_matches():
    text = r"""
    Discover the Secrets of the Universe

    Embark on a journey through the cosmos with our comprehensive guide to astronomy. Explore the vast expanse of space, delve into the mysteries of black holes and galaxies, and uncover the secrets of our planet's origins.

    The Universe Today: https://www.universetoday.com/
    NASA: https://www.nasa.gov/
    Guide: C:\Users\Public\Documents\NASA\Astronomy.pdf
    Video: /home/user/Downloads/Space Exploration.mp4
    """
    urls, no_urls = extract_matches(URL_REGEX, text)
    paths, no_paths = extract_matches(PATH_REGEX, no_urls)

    assert urls == ["https://www.universetoday.com/", "https://www.nasa.gov/"]
    assert paths == [
        r"C:\Users\Public\Documents\NASA\Astronomy.pdf",
        "/home/user/Downloads/Space Exploration.mp4",
    ]
