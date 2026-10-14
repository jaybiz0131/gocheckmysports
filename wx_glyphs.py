#!/usr/bin/env python3
"""wx_glyphs.py: GoCheckMyWeather's condition glyphs, vendored for the conditions strip (S-2b item 1).

GENERATED, NOT DRAWN HERE. Each string is WXIcons.svg(name, 20) from gocheckmyweather
assets/wx-icons.js at main 8a612d0 (13 October 2026), run in Node, so the strip on a Sports card
draws the same mark the Weather site and the app draw for the same sky. Regenerate rather than
edit: node renders the Weather file and this module is its output. COLORS is that file's palette.
"""

COLORS = {
 "sun": "#F5B83F",
 "sunLit": "#FFD569",
 "ray": "#C9861A",
 "moon": "#958967",
 "moonLit": "#D2C7A6",
 "cloud": "#7D8D9F",
 "cloudLit": "#BCC8D3",
 "dark": "#5E6D7F",
 "darkLit": "#8393A5",
 "rain": "#3E97D6",
 "snow": "#7FA6C8",
 "ice": "#5DB8D0",
 "hail": "#9DB8CF",
 "bolt": "#F2B632",
 "fog": "#7E8B98",
 "wind": "#7F8E9C",
 "dust": "#B08B5A",
 "smoke": "#8C8378",
 "funnel": "#6E7C8C",
 "trop": "#4C8FC7"
}

GLYPHS = {
    "clear-day": "<svg class=\"wxi wxi-clear-day\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><g stroke=\"#C9861A\" stroke-width=\"2.6\" stroke-linecap=\"round\"><line x1=\"16.40\" y1=\"10.00\" x2=\"19.40\" y2=\"10.00\"/><line x1=\"14.53\" y1=\"14.53\" x2=\"16.65\" y2=\"16.65\"/><line x1=\"10.00\" y1=\"16.40\" x2=\"10.00\" y2=\"19.40\"/><line x1=\"5.47\" y1=\"14.53\" x2=\"3.35\" y2=\"16.65\"/><line x1=\"3.60\" y1=\"10.00\" x2=\"0.60\" y2=\"10.00\"/><line x1=\"5.47\" y1=\"5.47\" x2=\"3.35\" y2=\"3.35\"/><line x1=\"10.00\" y1=\"3.60\" x2=\"10.00\" y2=\"0.60\"/><line x1=\"14.53\" y1=\"5.47\" x2=\"16.65\" y2=\"3.35\"/></g><circle cx=\"10\" cy=\"10\" r=\"4.2\" fill=\"#F5B83F\"/><circle cx=\"9.496\" cy=\"9.496\" r=\"4.2\" fill=\"#FFD569\"/></svg>",
    "clear-night": "<svg class=\"wxi wxi-clear-night\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M12.28 3.89 A6.5 6.5 0 1 0 12.28 16.11 A5.07 5.07 0 1 1 12.28 3.89Z\" fill=\"#958967\"/><path d=\"M11.63 3.24 A6.5 6.5 0 1 0 11.63 15.46 A5.07 5.07 0 1 1 11.63 3.24Z\" fill=\"#D2C7A6\"/></svg>",
    "partly-day": "<svg class=\"wxi wxi-partly-day\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><g stroke=\"#C9861A\" stroke-width=\"2.6\" stroke-linecap=\"round\"><line x1=\"13.10\" y1=\"7.50\" x2=\"16.10\" y2=\"7.50\"/><line x1=\"11.46\" y1=\"11.46\" x2=\"13.58\" y2=\"13.58\"/><line x1=\"7.50\" y1=\"13.10\" x2=\"7.50\" y2=\"16.10\"/><line x1=\"3.54\" y1=\"11.46\" x2=\"1.42\" y2=\"13.58\"/><line x1=\"1.90\" y1=\"7.50\" x2=\"-1.10\" y2=\"7.50\"/><line x1=\"3.54\" y1=\"3.54\" x2=\"1.42\" y2=\"1.42\"/><line x1=\"7.50\" y1=\"1.90\" x2=\"7.50\" y2=\"-1.10\"/><line x1=\"11.46\" y1=\"3.54\" x2=\"13.58\" y2=\"1.42\"/></g><circle cx=\"7.5\" cy=\"7.5\" r=\"3.4\" fill=\"#F5B83F\"/><circle cx=\"7.092\" cy=\"7.092\" r=\"3.4\" fill=\"#FFD569\"/><path d=\"M6.52 14.84 a2.76 2.76 0 0 1 1.47 -5.06 a3.91 3.91 0 0 1 7.13 -1.15 a2.85 2.85 0 0 1 3.36 6.21Z\" fill=\"#7D8D9F\"/><path d=\"M6.01 14.33 a2.76 2.76 0 0 1 1.47 -5.06 a3.91 3.91 0 0 1 7.13 -1.15 a2.85 2.85 0 0 1 3.36 6.21Z\" fill=\"#BCC8D3\"/></svg>",
    "partly-night": "<svg class=\"wxi wxi-partly-night\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M9.25 2.80 A5 5 0 1 0 9.25 12.20 A3.90 3.90 0 1 1 9.25 2.80Z\" fill=\"#958967\"/><path d=\"M8.75 2.30 A5 5 0 1 0 8.75 11.70 A3.90 3.90 0 1 1 8.75 2.30Z\" fill=\"#D2C7A6\"/><path d=\"M6.52 15.34 a2.76 2.76 0 0 1 1.47 -5.06 a3.91 3.91 0 0 1 7.13 -1.15 a2.85 2.85 0 0 1 3.36 6.21Z\" fill=\"#7D8D9F\"/><path d=\"M6.01 14.83 a2.76 2.76 0 0 1 1.47 -5.06 a3.91 3.91 0 0 1 7.13 -1.15 a2.85 2.85 0 0 1 3.36 6.21Z\" fill=\"#BCC8D3\"/></svg>",
    "cloudy": "<svg class=\"wxi wxi-cloudy\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M3.82 9.94 a2.16 2.16 0 0 1 1.15 -3.96 a3.06 3.06 0 0 1 5.58 -0.90 a2.23 2.23 0 0 1 2.63 4.86Z\" fill=\"#5E6D7F\"/><path d=\"M3.42 9.54 a2.16 2.16 0 0 1 1.15 -3.96 a3.06 3.06 0 0 1 5.58 -0.90 a2.23 2.23 0 0 1 2.63 4.86Z\" fill=\"#8393A5\"/><path d=\"M5.50 15.00 a3.00 3.00 0 0 1 1.60 -5.50 a4.25 4.25 0 0 1 7.75 -1.25 a3.10 3.10 0 0 1 3.65 6.75Z\" fill=\"#7D8D9F\"/><path d=\"M4.95 14.45 a3.00 3.00 0 0 1 1.60 -5.50 a4.25 4.25 0 0 1 7.75 -1.25 a3.10 3.10 0 0 1 3.65 6.75Z\" fill=\"#BCC8D3\"/></svg>",
    "fog": "<svg class=\"wxi wxi-fog\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><circle cx=\"14\" cy=\"6\" r=\"2.8\" fill=\"#F5B83F\"/><g stroke=\"#7E8B98\" stroke-width=\"2\" stroke-linecap=\"round\" fill=\"none\"><line x1=\"3\" y1=\"12\" x2=\"17\" y2=\"12\"/><line x1=\"5\" y1=\"15.5\" x2=\"15\" y2=\"15.5\"/><line x1=\"3\" y1=\"19\" x2=\"14\" y2=\"19\"/></g></svg>",
    "rain": "<svg class=\"wxi wxi-rain\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.72 11.24 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#5E6D7F\"/><path d=\"M2.10 10.62 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#8393A5\"/><g stroke=\"#3E97D6\" stroke-width=\"2.1\" stroke-linecap=\"round\" fill=\"none\"><line x1=\"8.5\" y1=\"14\" x2=\"7.1\" y2=\"18\"/><line x1=\"13\" y1=\"14\" x2=\"11.6\" y2=\"18\"/></g></svg>",
    "heavy-rain": "<svg class=\"wxi wxi-heavy-rain\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.72 11.24 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#4E5C6D\"/><path d=\"M2.10 10.62 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#5E6D7F\"/><g stroke=\"#3E97D6\" stroke-width=\"2.1\" stroke-linecap=\"round\" fill=\"none\"><line x1=\"7\" y1=\"14\" x2=\"5.6\" y2=\"18\"/><line x1=\"11\" y1=\"14\" x2=\"9.6\" y2=\"18\"/><line x1=\"15\" y1=\"14\" x2=\"13.6\" y2=\"18\"/></g></svg>",
    "thunderstorm": "<svg class=\"wxi wxi-thunderstorm\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.72 10.74 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#4E5C6D\"/><path d=\"M2.10 10.12 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#5E6D7F\"/><path d=\"M11 11.5 L8 16 L10.4 16 L9 20 L13.4 14.3 L11 14.3 L12.4 11.5Z\" fill=\"#F2B632\"/></svg>",
    "snow": "<svg class=\"wxi wxi-snow\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.72 11.24 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#7D8D9F\"/><path d=\"M2.10 10.62 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#BCC8D3\"/><circle cx=\"8\" cy=\"16.5\" r=\"1.6\" fill=\"#7FA6C8\"/><circle cx=\"13\" cy=\"16.5\" r=\"1.6\" fill=\"#7FA6C8\"/></svg>",
    "sleet": "<svg class=\"wxi wxi-sleet\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><path d=\"M2.72 11.24 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#7D8D9F\"/><path d=\"M2.10 10.62 a3.36 3.36 0 0 1 1.79 -6.16 a4.76 4.76 0 0 1 8.68 -1.40 a3.47 3.47 0 0 1 4.09 7.56Z\" fill=\"#BCC8D3\"/><g stroke=\"#3E97D6\" stroke-width=\"2\" stroke-linecap=\"round\" fill=\"none\"><line x1=\"8\" y1=\"14\" x2=\"6.8\" y2=\"18\"/></g><circle cx=\"13\" cy=\"16.5\" r=\"1.6\" fill=\"#7FA6C8\"/></svg>",
    "wind": "<svg class=\"wxi wxi-wind\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><g fill=\"none\" stroke=\"#7F8E9C\" stroke-width=\"1.9\" stroke-linecap=\"round\"><path d=\"M2 8 H12 a2.6 2.6 0 1 0 -2.6 -2.6\"/><path d=\"M2 12.5 H15 a2.6 2.6 0 1 1 -2.6 2.6\"/></g></svg>",
    "high-wind": "<svg class=\"wxi wxi-high-wind\" viewBox=\"0 0 20 20\" width=\"20\" height=\"20\" aria-hidden=\"true\" focusable=\"false\"><g fill=\"none\" stroke=\"#7F8E9C\" stroke-width=\"1.9\" stroke-linecap=\"round\"><path d=\"M2 8 H12 a2.6 2.6 0 1 0 -2.6 -2.6\"/><path d=\"M2 12.5 H15 a2.6 2.6 0 1 1 -2.6 2.6\"/><path d=\"M2 16.7 H9\"/></g></svg>",
}


def for_sky(sky, is_daytime=True):
    """The glyph for an NWS short forecast. The words are NWS's; the order puts the most
    severe word first, as the Weather site's condition key does."""
    s = (sky or "").lower()
    night = is_daytime is False
    if "thunder" in s:
        return "thunderstorm"
    if "snow" in s or "flurr" in s:
        return "snow"
    if "sleet" in s or "freezing" in s:
        return "sleet"
    if "heavy rain" in s:
        return "heavy-rain"
    if "rain" in s or "shower" in s or "drizzle" in s:
        return "rain"
    if "fog" in s:
        return "fog"
    if "partly" in s or "mostly sunny" in s or "mostly clear" in s:
        return "partly-night" if night else "partly-day"
    if "cloudy" in s or "overcast" in s:
        return "cloudy"
    if "sunny" in s or "clear" in s:
        return "clear-night" if night else "clear-day"
    return None
