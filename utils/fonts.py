import re

def _convert(text: str, upper_start: int, lower_start: int, num_start: int = None) -> str:
    res = []
    for c in text:
        o = ord(c)
        if 65 <= o <= 90:    # A-Z
            res.append(chr(o - 65 + upper_start))
        elif 97 <= o <= 122:  # a-z
            res.append(chr(o - 97 + lower_start))
        elif 48 <= o <= 57 and num_start is not None:  # 0-9
            res.append(chr(o - 48 + num_start))
        else:
            res.append(c)
    return "".join(res)

def bold_sans(text: str) -> str:
    """Converts letters and digits to Bold Sans-Serif (e.g. 𝗔𝗕𝗖, 𝗮𝗯𝗰, 𝟬𝟵)."""
    return _convert(text, 0x1D5D4, 0x1D5EE, 0x1D7EC)

def sans_normal(text: str) -> str:
    """Converts letters and digits to Sans-Serif Normal (e.g. 𝖠𝖡𝖢, 𝖺𝖻𝖼, 𝟢𝟫)."""
    return _convert(text, 0x1D5A0, 0x1D5BA, 0x1D7E2)

def bold_serif(text: str) -> str:
    """Converts letters and digits to Bold Serif (e.g. 𝐀𝐁𝐂, 𝐚𝐛𝐜, 𝟎𝟗)."""
    return _convert(text, 0x1D400, 0x1D41A, 0x1D7CE)

def monospace_sans(text: str) -> str:
    """Converts letters and digits to Monospace Typewriter (e.g. 𝙰𝙱𝙲, 𝚊𝚋𝚌, 𝟶𝟿)."""
    return _convert(text, 0x1D670, 0x1D68A, 0x1D7F6)

def italic_sans(text: str) -> str:
    """Converts letters to Italic Sans-Serif (e.g. 𝘈𝘉𝘊, 𝘢𝘣𝘤)."""
    return _convert(text, 0x1D608, 0x1D622)

def bold_italic_sans(text: str) -> str:
    """Converts letters to Bold Italic Sans-Serif (e.g. 𝘼𝘽𝘾, 𝙖𝙗𝙘)."""
    return _convert(text, 0x1D63C, 0x1D656)

def stylize_html(text: str, styler_func) -> str:
    """
    Applies styler_func to the text content while keeping HTML tags, URLs,
    and Telegram usernames (@username) untouched.
    """
    if not text:
        return ""
    # Matches: HTML tags, URLs (http/https), Telegram user mentions, or numbers/hashes like SHN-...
    pattern = r'(<[^>]+>|https?://\S+|t\.me/\S+|@\w+|SHN-[0-9A-F]+)'
    parts = re.split(pattern, text)
    new_parts = []
    for part in parts:
        if not part:
            continue
        if (
            (part.startswith('<') and part.endswith('>')) or 
            part.startswith('http://') or 
            part.startswith('https://') or 
            part.startswith('t.me/') or 
            part.startswith('@') or
            part.startswith('SHN-')
        ):
            new_parts.append(part)
        else:
            new_parts.append(styler_func(part))
    return "".join(new_parts)
