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


# ─── Premium Visual Helpers ───────────────────────────────────────────────────

from datetime import datetime

def header(emoji: str, title: str) -> str:
    """Sleek header for mobile screens."""
    t = bold_sans(title.upper())
    return f"<b>{emoji} {t}</b>\n━━━━━━━━━━━━━━━━━━━━\n"

def sub_header(emoji: str, title: str) -> str:
    """Sleek section sub-header."""
    return f"<b>{emoji} {bold_sans(title.upper())}</b>\n"

def divider() -> str:
    return "━━━━━━━━━━━━━━━━━━━━\n"

def light_divider() -> str:
    return "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈\n"

def mini_divider() -> str:
    return "· · · · · · · · · ·\n"

def footer_box(text: str) -> str:
    """Creates a native Telegram blockquote footer block for perfect mobile wrapping."""
    styled = stylize_html(text, sans_normal)
    return f"<blockquote>💡 {styled}</blockquote>"

def stat_line(emoji: str, label: str, value: str) -> str:
    """Formatted stat line for dashboards."""
    return f"  {emoji} <b>{sans_normal(label)}:</b> {value}\n"

def stat_line_bold(emoji: str, label: str, value: str) -> str:
    """Formatted stat line with bold value."""
    return f"  {emoji} <b>{sans_normal(label)}:</b> <b>{value}</b>\n"

def step_indicator(steps: list, current: int) -> str:
    """Visual step progress indicator."""
    lines = []
    for i, (emoji, label) in enumerate(steps):
        if i < current:
            lines.append(f"  ✅ {sans_normal(label)}")
        elif i == current:
            lines.append(f"  🔄 <b>{sans_normal(label)}</b>  ◀")
        else:
            lines.append(f"  ⬜ <i>{sans_normal(label)}</i>")
    return "\n".join(lines) + "\n"

def progress_bar(current: int, total: int, length: int = 10) -> str:
    """Visual progress bar with percentage."""
    if total <= 0:
        filled = 0
        pct = 0
    else:
        ratio = min(current / total, 1.0)
        filled = int(ratio * length)
        pct = int(ratio * 100)
    bar = "█" * filled + "░" * (length - filled)
    return f"<code>{bar}</code> {bold_sans(str(pct) + '%')} ({current}/{total})"

def stock_bar(available: int, total: int = 50) -> str:
    """Compact stock level indicator."""
    if total <= 0: total = max(available, 1)
    ratio = min(available / total, 1.0)
    bars = int(ratio * 8)
    if available == 0:
        return "▱▱▱▱▱▱▱▱ 🔴"
    elif ratio < 0.2:
        return "▰" * bars + "▱" * (8 - bars) + " ⚠️"
    else:
        return "▰" * bars + "▱" * (8 - bars) + " 🟢"

def tier_badge(order_count: int) -> str:
    """Loyalty tier badge based on order count."""
    if order_count >= 31: return "💎 Diamond Member"
    if order_count >= 16: return "🥇 Gold Member"
    if order_count >= 6:  return "🥈 Silver Member"
    if order_count >= 1:  return "🥉 Bronze Member"
    return "🆕 New Member"

def tier_icon(order_count: int) -> str:
    """Just the tier icon."""
    if order_count >= 31: return "💎"
    if order_count >= 16: return "🥇"
    if order_count >= 6:  return "🥈"
    if order_count >= 1:  return "🥉"
    return "🆕"

def time_greeting() -> str:
    """Dynamic greeting based on time of day."""
    hour = datetime.now().hour
    if 5 <= hour < 12:   return "🌅 Good Morning"
    if 12 <= hour < 17:  return "☀️ Good Afternoon"
    if 17 <= hour < 21:  return "🌆 Good Evening"
    return "🌙 Hey Night Owl"

def price_tag(amount) -> str:
    """Formatted price display."""
    return f"<b>₹{amount}</b>"

def code_block(code: str) -> str:
    """Sleek mobile-friendly coupon code display."""
    return f"<blockquote>🔑 <code>{code}</code></blockquote>"

def format_coupon_code(code: str) -> str:
    """
    Parses and formats a coupon code string.
    Supports:
    1. Web URLs (renders as clickable HTML links)
    2. Gift Cards with Code + PIN (splits by Delimiter and renders them as separate copyable code blocks)
    3. Normal code strings (renders as standard code blocks)
    """
    code_stripped = code.strip()
    
    # 1. Check if it's a URL
    is_url = False
    if code_stripped.startswith(("http://", "https://")):
        is_url = True
    elif re.match(r'^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,6}(/\S*)?$', code_stripped):
        is_url = True
        
    if is_url:
        url = code_stripped if code_stripped.startswith(("http://", "https://")) else f"https://{code_stripped}"
        return f"<blockquote>🔗 <b>Link:</b> <a href='{url}'>{code_stripped}</a></blockquote>"
        
    # 2. Check if it contains a PIN (split by |, /, :, or spaces)
    pin_keywords = [r'\s*\|\s*', r'\s*/\s*', r'\s*PIN:\s*', r'\s*pin:\s*', r'\s*Pin:\s*', r'\s*PIN\s+', r'\s*pin\s+']
    for pattern in pin_keywords:
        match = re.split(pattern, code_stripped, maxsplit=1, flags=re.IGNORECASE)
        if len(match) == 2 and match[0].strip() and match[1].strip():
            c_part = match[0].strip()
            p_part = match[1].strip()
            if c_part.lower().startswith("code:"):
                c_part = c_part[5:].strip()
            return f"<blockquote>🔑 <b>Code:</b> <code>{c_part}</code>\n📌 <b>PIN:</b> <code>{p_part}</code></blockquote>"

    # Handle simple space-separated parts if it matches exactly two alphanumeric/number sequences of code + pin
    space_split = code_stripped.split()
    if len(space_split) == 2:
        c_part, p_part = space_split[0], space_split[1]
        if len(p_part) <= 8:
            return f"<blockquote>🔑 <b>Code:</b> <code>{c_part}</code>\n📌 <b>PIN:</b> <code>{p_part}</code></blockquote>"

    # 3. Default: standard single code block
    return code_block(code_stripped)

def order_id_display(order_id: str) -> str:
    """Formatted order ID display."""
    return f"📋 <code>{order_id}</code>"

def countdown_text(minutes: int) -> str:
    """Visual countdown timer."""
    return f"⏰ <b>{minutes}:00</b> {sans_normal('remaining')}"


from html.parser import HTMLParser
import html as _html

class TelegramHTMLSanitizer(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self.tag_stack = []

    def handle_starttag(self, tag, attrs):
        # List of supported tags in Telegram HTML
        supported = {'b', 'strong', 'i', 'em', 'u', 'ins', 's', 'strike', 'del', 'span', 'a', 'code', 'pre', 'blockquote', 'tg-spoiler', 'tg-emoji'}
        
        # Translate headers to bold
        if tag in {'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}:
            self.result.append("<b>")
            self.tag_stack.append("b")
        elif tag in {'p', 'div', 'br', 'section'}:
            if tag == 'br':
                self.result.append("\n")
            elif tag in {'p', 'div', 'section'} and self.result and not self.result[-1].endswith("\n"):
                self.result.append("\n")
            self.tag_stack.append(None)
        elif tag in supported:
            # Filter attributes
            filtered_attrs = []
            for name, value in attrs:
                if tag == 'a' and name == 'href':
                    filtered_attrs.append(f'href="{_html.escape(value)}"')
                elif tag == 'span' and name == 'class' and value == 'tg-spoiler':
                    filtered_attrs.append(f'class="tg-spoiler"')
                elif tag == 'tg-emoji' and name == 'emoji-id':
                    filtered_attrs.append(f'emoji-id="{_html.escape(value)}"')
            
            attr_str = " " + " ".join(filtered_attrs) if filtered_attrs else ""
            self.result.append(f"<{tag}{attr_str}>")
            self.tag_stack.append(tag)
        else:
            self.tag_stack.append(None)

    def handle_endtag(self, tag):
        if not self.tag_stack:
            return
        
        corresponding_start = self.tag_stack.pop()
        if corresponding_start:
            self.result.append(f"</{corresponding_start}>")
        elif tag in {'p', 'div', 'section'} and self.result and not self.result[-1].endswith("\n"):
            self.result.append("\n")

    def handle_data(self, data):
        # Escape any raw < or > in text
        self.result.append(_html.escape(data))

    def handle_entityref(self, name):
        self.result.append(f"&{name};")

    def handle_charref(self, name):
        self.result.append(f"&#{name};")

def sanitize_telegram_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    parser = TelegramHTMLSanitizer()
    parser.feed(raw_html)
    parser.close()
    
    # Clean up double escapes (e.g. &amp;lt; to &lt;) if any
    cleaned = "".join(parser.result)
    # Restore basic standard entities so Telegram can parse them
    cleaned = cleaned.replace("&amp;lt;", "&lt;").replace("&amp;gt;", "&gt;").replace("&amp;amp;", "&amp;")
    return cleaned


def escape_html(text: str) -> str:
    """Escapes HTML special characters in string to prevent Telegram HTML parser crashes."""
    if not text:
        return ""
    return _html.escape(text)
