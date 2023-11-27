import re
import base64
from typing import Self, Literal, ClassVar, runtime_checkable, Protocol, Callable
from dataclasses import dataclass
import textwrap
from pathlib import Path

from pydantic import TypeAdapter
from rich.console import Group
from rich.panel import Panel
import pytest
from twidge.widgets import Close, EditString, Framed



STYLES = {
    "system": "bright_blue italic on black",
    "user": "bright_red on black",
    "assistant": "bright_green on black",
    "border": "bright_black bold not italic on black",
    "editor_border": "bright_yellow on black",
}

@runtime_checkable
class Objectable(Protocol):
    def object(self) -> dict:
        ...


def objectify(inst):
    match inst:
        case Objectable():
            return inst.object()
        case _:
            return inst


@dataclass
class TextContentPart:
    text: str

    def object(self):
        return {'type': 'text', 'text': self.text}

    def __rich__(self):
        return self.text


@dataclass
class ImageContentPart:
    url: str

    def object(self):
        return {
            'type': 'image_url',
            'image_url': {
                'url': self.url
            }
        }

    def __rich__(self):
        return f'[link={self.url}]{self.url}[/link]'


type TextContent = str
type MultiModalContent = list[TextContentPart | ImageContentPart]


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str

    def object(self):
        return {
            'id': self.id,
            'type': 'function',
            'function': {
                'name': self.name,
                'arguments': self.arguments
            }
        }


@dataclass
class ChatMessage[RoleType: str, ContentType: (TextContent, MultiModalContent)]:
    role: RoleType
    content: ContentType

    def object(self):
        return {
            'role': self.role,
            'content': objectify(self.content)
        }

    def __rich__(self):
        return Panel.fit(
            self.content,
            title=self.role,
            title_align="left",
            style=STYLES[self.role],
            border_style=STYLES['border'],
        )

@dataclass
class ChatMessageToolCall[RoleType: str, ContentType: (TextContent, MultiModalContent)]:
    content: ContentType
    tool_calls: list[ToolCall] | None
    role: RoleType

    def object(self):
        return {
            'role': self.role,
            'content': self.content,
            'tool_calls': [call.json() for call in self.tool_calls]
        }

    def __rich__(self):
        return Panel.fit(
            Group(self.content, self.tool_calls),
            title=self.role,
            title_align="left",
            style=STYLES[self.role],
            border_style=STYLES['border'],
        )

@dataclass
class ChatMessageToolResult[RoleType: str, ContentType: (TextContent, MultiModalContent)]:
    content: ContentType
    tool_call_id: str
    name: str
    role: RoleType

    def object(self):
        return {
            'role': self.role,
            'tool_call_id': self.tool_call_id,
            'name': self.name,
            'content': self.content
        }

    def __rich__(self):
        return Panel.fit(
            Group(self.tool_call_id, self.name, self.content),
            title=self.role,
            title_align="left",
            style=STYLES[self.role],
            border_style=STYLES['border'],
        )


type TextChatMessage = ChatMessage[Literal['system', 'user', 'assistant'], TextContent]
type TextWithToolsChatMessage = (
    ChatMessage[Literal['system', 'user', 'assistant'], TextContent] |
    ChatMessageToolCall[Literal['assistant'], TextContent] |
    ChatMessageToolResult[Literal['tool'], TextContent]
)
type MultiModalChatMessage = (
    ChatMessage[Literal['system', 'assistant'], TextContent] |
    ChatMessage[Literal['system', 'user', 'assistant'], MultiModalContent]
)


@dataclass
class Messages[MessageType]:
    messages: list[MessageType]
    watchers: list[Callable]

    def notify(self, fn: Callable):
        self.watchers.append(fn)

    
    def post(self, message: Message):
        self.messages.append(message)
        for fn in self.watchers:
            fn(message)
        if message.content.text or message.content.image_urls:
            print(message)


def parse(cls, obj):
    return TypeAdapter(
        cls,
        config={'extra': 'forbid'}
    ).validate_python(obj)


def construct(cls, **properties):
    return parse(cls, properties)


def compose(role: str, content: str = '', extract_images: bool = True):
    text = Close(
        Framed(
            EditString(
                content, text_style=STYLES[role], cursor_line_style=STYLES[role]
            ),
            title=role,
            title_align="left",
            style=STYLES['editor_border'],
        )
    ).run()
    if not extract_images:
        return ChatMessage(role, text)
    content = extract_urls(text) if extract_images else text
    return ChatMessage(role, content)


def extract_urls(content: TextContent | MultiModalContent) -> TextContent | MultiModalContent:
    match content:
        case str():
            text, urls = _extract_image_urls(content)
            if not urls:
                return text
            return [
                TextContentPart(text),
                *(ImageContentPart(url) for url in urls)
            ]
        case list():
            parts = []
            for part in content:
                match part:
                    case TextContentPart():
                        text, urls = _extract_image_urls(part)
                        if not urls:
                            parts.append(part)
                        else:
                            parts.append(TextContentPart(text))
                            parts.extend(ImageContentPart(url) for url in urls)
                    case ImageContentPart():
                        parts.extend(part)
            return parts
                

    

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
