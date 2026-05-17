import csv
import os
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional

import pandas as pd


DATE_FORMAT = "%Y-%m-%d"
QtCore = None
QtGui = None
QtWidgets = None
QPrinter = None


@dataclass
class DateRange:
    start: Optional[datetime] = None
    end: Optional[datetime] = None

    @classmethod
    def last_30_days(cls):
        today = datetime.now()
        return cls(start=today - timedelta(days=30), end=today)

    @classmethod
    def from_dates(cls, start_date, end_date):
        return cls(start=_parse_datetime(start_date), end=_parse_datetime(end_date))

    def contains(self, value):
        parsed = _parse_datetime(value)
        if parsed is None:
            return self.start is None and self.end is None
        if self.start and parsed.date() < self.start.date():
            return False
        if self.end and parsed.date() > self.end.date():
            return False
        return True


@dataclass
class StatisticsSummary:
    sent_emails: int = 0
    positive_replies: int = 0
    negative_replies: int = 0
    second_emails: int = 0
    potential_earnings: float = 0
    daily_sent: Dict[str, int] = field(default_factory=dict)
    daily_positive_replies: Dict[str, int] = field(default_factory=dict)
    daily_negative_replies: Dict[str, int] = field(default_factory=dict)
    daily_second_emails: Dict[str, int] = field(default_factory=dict)

    @property
    def total_replies(self):
        return self.positive_replies + self.negative_replies

    @property
    def positive_rate(self):
        if self.total_replies == 0:
            return 0
        return self.positive_replies / self.total_replies


class StatisticsCalculator:
    def __init__(
        self,
        report_path,
        followup_report_path,
        negative_words=None,
    ):
        self.report_path = report_path
        self.followup_report_path = followup_report_path
        self.negative_words = negative_words or [
            "no",
            "stop",
            "nope",
            "nah",
            "not interested",
            "decline",
            "can't",
            "won't",
            "don't want",
        ]

    def calculate(self, inbox_tables=None, date_range=None, product_price=0):
        inbox_tables = inbox_tables or []
        date_range = date_range or DateRange()
        sent_rows = self._read_sent_rows(self.report_path, date_range)
        followup_rows = self._read_sent_rows(self.followup_report_path, date_range)
        reply_counts = self._count_replies(inbox_tables, date_range)
        product_price_value = _parse_money(product_price)

        return StatisticsSummary(
            sent_emails=len(sent_rows),
            positive_replies=reply_counts["positive"],
            negative_replies=reply_counts["negative"],
            second_emails=len(followup_rows),
            potential_earnings=reply_counts["positive"] * product_price_value,
            daily_sent=_daily_counts(sent_rows),
            daily_positive_replies=dict(reply_counts["daily_positive"]),
            daily_negative_replies=dict(reply_counts["daily_negative"]),
            daily_second_emails=_daily_counts(followup_rows),
        )

    def _read_sent_rows(self, path, date_range):
        rows = []
        if not path or not os.path.exists(path):
            return rows

        try:
            with open(path, newline="", encoding="utf-8") as csvfile:
                for row in csv.DictReader(csvfile):
                    status = str(row.get("STATUS", "")).strip().lower()
                    if status == "status":
                        continue
                    if status != "sent":
                        continue
                    if not date_range.contains(row.get("DATE")):
                        continue
                    rows.append(row)
        except Exception:
            return []
        return rows

    def _count_replies(self, inbox_tables, date_range):
        result = {
            "positive": 0,
            "negative": 0,
            "daily_positive": defaultdict(int),
            "daily_negative": defaultdict(int),
        }
        for table in inbox_tables:
            if table is None or getattr(table, "empty", True):
                continue
            for _, row in table.iterrows():
                if _is_sent_mail(row):
                    continue
                row_date = row.get("date", "")
                if not date_range.contains(row_date):
                    continue
                day = _date_key(row_date)
                if self._is_positive_reply(row.get("body", ""), row.get("to_mail", "")):
                    result["positive"] += 1
                    if day:
                        result["daily_positive"][day] += 1
                else:
                    result["negative"] += 1
                    if day:
                        result["daily_negative"][day] += 1
        return result

    def _is_positive_reply(self, body, to_mail=""):
        text = _reply_text(body, to_mail)
        sentiment_score = _sentiment_polarity(text)
        negative_words = [word.strip() for word in self.negative_words if str(word).strip()]
        if negative_words:
            pattern = re.compile(
                r"\b(" + "|".join(map(re.escape, negative_words)) + r")\b",
                re.IGNORECASE,
            )
            if pattern.search(text):
                sentiment_score = -1
        return sentiment_score >= 0


def _sentiment_polarity(text):
    try:
        from textblob import TextBlob
        return TextBlob(text).sentiment.polarity
    except Exception:
        lowered = str(text or "").lower()
        negative_terms = [
            "awful",
            "bad",
            "disappointing",
            "horrible",
            "poor",
            "terrible",
            "unhappy",
            "upset",
            "worst",
        ]
        positive_terms = [
            "good",
            "great",
            "happy",
            "interested",
            "love",
            "perfect",
            "thanks",
            "yes",
        ]
        if any(term in lowered for term in negative_terms):
            return -1
        if any(term in lowered for term in positive_terms):
            return 1
        return 0


def _daily_counts(rows):
    counts = defaultdict(int)
    for row in rows:
        day = _date_key(row.get("DATE"))
        if day:
            counts[day] += 1
    return dict(counts)


def _date_key(value):
    parsed = _parse_datetime(value)
    if parsed is None:
        return ""
    return parsed.strftime(DATE_FORMAT)


def _parse_datetime(value):
    if value is None or value == "":
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    try:
        timestamp = pd.to_datetime(value, errors="coerce")
        if pd.isna(timestamp):
            return None
        return timestamp.to_pydatetime()
    except Exception:
        return None


def _parse_money(value):
    try:
        text = str(value).replace("$", "").replace(",", "").strip()
        parsed = float(text)
        return parsed if parsed > 0 else 0
    except Exception:
        return 0


def _reply_text(body, to_mail):
    text = str(body or "").encode("utf-8", errors="ignore").decode("utf-8")
    split_token = str(to_mail or "")
    if split_token and split_token in text:
        return text.split(split_token)[0]
    return text


def _is_sent_mail(row):
    if "is_sent" not in row:
        return False
    value = row.get("is_sent")
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes")
    return bool(value)


def format_currency(value):
    try:
        amount = float(value)
    except Exception:
        amount = 0
    if amount >= 1000:
        return "${:,.0f}".format(amount)
    return "${:,.2f}".format(amount).rstrip("0").rstrip(".")


def format_number(value):
    try:
        return "{:,}".format(int(value))
    except Exception:
        return "0"


def _ensure_qt():
    global QtCore, QtGui, QtWidgets, QPrinter
    if QtCore is None:
        from PyQt5 import QtCore as _QtCore
        from PyQt5 import QtGui as _QtGui
        from PyQt5 import QtWidgets as _QtWidgets
        from PyQt5.QtPrintSupport import QPrinter as _QPrinter
        QtCore = _QtCore
        QtGui = _QtGui
        QtWidgets = _QtWidgets
        QPrinter = _QPrinter


def create_statistics_report_preview(parent=None):
    _ensure_qt()

    class StatisticsReportPreview(QtWidgets.QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            self.summary = StatisticsSummary()
            self.logo_path = ""
            self.title = "Outreach Performance"
            self.date_label = "Last 30 days"
            self.setMinimumHeight(900)
            self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

        def set_report(self, summary, logo_path="", title=None, date_label=""):
            self.summary = summary or StatisticsSummary()
            self.logo_path = logo_path or ""
            if title:
                self.title = title
            self.date_label = date_label or ""
            self.update()

        def paintEvent(self, event):
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            rect = self.rect().adjusted(18, 18, -18, -18)
            draw_statistics_report(
                painter=painter,
                rect=rect,
                summary=self.summary,
                logo_path=self.logo_path,
                title=self.title,
                date_label=self.date_label,
                generated_label="Preview",
            )
            painter.end()

    return StatisticsReportPreview(parent)


def export_statistics_pdf(path, summary, logo_path="", title="Outreach Performance", date_label=""):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception as exc:
        raise RuntimeError(
            "ReportLab is required for PDF export. Install it with: pip install reportlab"
        ) from exc

    summary = summary or StatisticsSummary()
    pdf = canvas.Canvas(path, pagesize=A4)
    width, height = A4
    margin = 36
    content_width = width - (margin * 2)
    generated_label = datetime.now().strftime("Generated %Y-%m-%d %H:%M")

    _rl_round_rect(pdf, margin, margin, content_width, height - margin * 2, "#f7f8fb", "#dfe5ee", 14)
    left = margin + 30
    right = width - margin - 30
    top = height - margin - 30

    _rl_text(pdf, left, top, "CLIENT CAMPAIGN REPORT", 10.5, "#697586", bold=True)
    _rl_text(pdf, left, top - 30, title, 24, "#111827", bold=True)
    if date_label:
        _rl_text(pdf, left, top - 54, date_label, 9.5, "#667085", bold=True)
    _rl_logo(pdf, right - 108, top - 48, 108, 48, logo_path, ImageReader)
    _rl_accent_rule(pdf, left, top - 74, right - left)

    cards_y = top - 158
    gap = 12
    card_width = (right - left - gap * 3) / 4
    for index, (label, value, color) in enumerate(
        [
            ("Sent", format_number(summary.sent_emails), "#111827"),
            ("Positive", format_number(summary.positive_replies), "#087443"),
            ("Follow-ups", format_number(summary.second_emails), "#111827"),
            ("Potential", format_currency(summary.potential_earnings), "#111827"),
        ]
    ):
        x = left + index * (card_width + gap)
        _rl_kpi_card(pdf, x, cards_y, card_width, 84, label, value, color)

    chart_y = cards_y - 230
    _rl_chart_panel(pdf, left, chart_y, right - left, 196, summary)

    lower_y = chart_y - 160
    panel_gap = 18
    panel_width = (right - left - panel_gap) / 2
    _rl_reply_quality_panel(pdf, left, lower_y, panel_width, 132, summary)
    _rl_email_mix_panel(pdf, left + panel_width + panel_gap, lower_y, panel_width, 132, summary)

    footer_y = margin + 34
    _rl_summary_strip(pdf, left, footer_y, right - left, 72, summary)
    _rl_text_right(pdf, right, margin + 14, generated_label, 7.5, "#98a2b3")
    pdf.showPage()
    pdf.save()


def _rl_round_rect(pdf, x, y, width, height, fill, stroke, radius):
    pdf.saveState()
    pdf.setFillColor(_rl_color(fill))
    pdf.setStrokeColor(_rl_color(stroke))
    pdf.setLineWidth(0.8)
    pdf.roundRect(x, y, width, height, radius, stroke=1, fill=1)
    pdf.restoreState()


def _rl_text(pdf, x, y, text, size, color, bold=False):
    pdf.saveState()
    pdf.setFillColor(_rl_color(color))
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawString(x, y, str(text))
    pdf.restoreState()


def _rl_text_right(pdf, x, y, text, size, color, bold=False):
    pdf.saveState()
    pdf.setFillColor(_rl_color(color))
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawRightString(x, y, str(text))
    pdf.restoreState()


def _rl_text_center(pdf, x, y, text, size, color, bold=False):
    pdf.saveState()
    pdf.setFillColor(_rl_color(color))
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawCentredString(x, y, str(text))
    pdf.restoreState()


def _rl_accent_rule(pdf, x, y, width):
    pdf.saveState()
    pdf.setStrokeColor(_rl_color("#028fc3"))
    pdf.setLineWidth(1.2)
    pdf.line(x, y, x + width, y)
    pdf.setStrokeColor(_rl_color("#087443"))
    pdf.line(x + width * 0.45, y, x + width * 0.62, y)
    pdf.setStrokeColor(_rl_color("#c2410c"))
    pdf.line(x + width * 0.62, y, x + width * 0.75, y)
    pdf.restoreState()


def _rl_kpi_card(pdf, x, y, width, height, label, value, value_color):
    _rl_round_rect(pdf, x, y, width, height, "#ffffff", "#dfe3ea", 9)
    _rl_text(pdf, x + 16, y + height - 30, label, 9.5, "#667085", bold=True)
    _rl_text(pdf, x + 16, y + 24, value, 23, value_color, bold=True)


def _rl_chart_panel(pdf, x, y, width, height, summary):
    _rl_round_rect(pdf, x, y, width, height, "#f8fbff", "#d5e2ef", 10)
    _rl_text(pdf, x + 18, y + height - 28, "Outreach Performance", 12.5, "#111827", bold=True)
    _rl_text(pdf, x + 18, y + height - 48, "Campaign volume and response movement", 8.5, "#667085")
    plot_left = x + 40
    plot_bottom = y + 46
    plot_width = width - 82
    plot_height = height - 112
    pdf.saveState()
    pdf.setStrokeColor(_rl_color("#d8e6f2"))
    pdf.setLineWidth(0.6)
    for index in range(1, 4):
        grid_y = plot_bottom + plot_height * index / 4
        pdf.line(plot_left, grid_y, plot_left + plot_width, grid_y)
    pdf.setStrokeColor(_rl_color("#028fc3"))
    pdf.setLineWidth(1.2)
    pdf.line(plot_left, plot_bottom, plot_left + plot_width, plot_bottom)
    pdf.line(plot_left, plot_bottom, plot_left, plot_bottom + plot_height)
    pdf.restoreState()

    values = [
        ("Sent", summary.sent_emails, "#028fc3"),
        ("Positive", summary.positive_replies, "#087443"),
        ("Negative", summary.negative_replies, "#c2410c"),
        ("Follow-ups", summary.second_emails, "#475467"),
    ]
    max_value = max([value for _, value, _ in values] + [1])
    bar_width = min(52, plot_width / 8)
    spacing = (plot_width - bar_width * len(values)) / (len(values) + 1)
    cursor = plot_left + spacing
    for label, value, color in values:
        bar_height = max(3 if value else 0, (plot_height - 12) * (value / max_value))
        pdf.saveState()
        pdf.setFillColor(_rl_color(color))
        pdf.roundRect(cursor, plot_bottom, bar_width, bar_height, 5, stroke=0, fill=1)
        pdf.restoreState()
        _rl_text_center(pdf, cursor + bar_width / 2, plot_bottom + bar_height + 8, format_number(value), 8, "#111827", bold=True)
        _rl_text_center(pdf, cursor + bar_width / 2, plot_bottom - 18, label, 7.5, "#667085")
        cursor += bar_width + spacing


def _rl_reply_quality_panel(pdf, x, y, width, height, summary):
    _rl_round_rect(pdf, x, y, width, height, "#ffffff", "#e5e7eb", 9)
    _rl_text(pdf, x + 16, y + height - 26, "Reply Quality", 12, "#111827", bold=True)
    positive_pct = int(round(summary.positive_rate * 100))
    _rl_text(pdf, x + 16, y + height - 58, f"{positive_pct}% positive", 17, "#087443", bold=True)
    _rl_text(pdf, x + 16, y + height - 76, "reply mix", 10, "#087443", bold=True)
    _rl_text(pdf, x + 16, y + height - 96, f"{format_number(summary.positive_replies)} positive, {format_number(summary.negative_replies)} negative", 8.5, "#667085")
    _rl_donut(pdf, x + width - 94, y + 30, 64, [summary.positive_replies, summary.negative_replies], ["#087443", "#c2410c"])
    _rl_legend(pdf, x + 16, y + 18, [("Positive", "#087443"), ("Negative", "#c2410c")])


def _rl_email_mix_panel(pdf, x, y, width, height, summary):
    _rl_round_rect(pdf, x, y, width, height, "#ffffff", "#e5e7eb", 9)
    _rl_text(pdf, x + 16, y + height - 26, "Email Mix", 12, "#111827", bold=True)
    _rl_text(pdf, x + 16, y + height - 58, format_currency(summary.potential_earnings), 18, "#111827", bold=True)
    _rl_text(pdf, x + 16, y + height - 80, "Potential from interested replies", 9, "#667085")
    _rl_donut(pdf, x + width - 94, y + 30, 64, [summary.sent_emails, summary.second_emails, summary.positive_replies], ["#028fc3", "#475467", "#087443"])
    _rl_legend(pdf, x + 16, y + 18, [("Sent", "#028fc3"), ("Follow-ups", "#475467"), ("Positive", "#087443")])


def _rl_summary_strip(pdf, x, y, width, height, summary):
    _rl_round_rect(pdf, x, y, width, height, "#ffffff", "#e5e7eb", 9)
    reply_total = summary.total_replies
    reply_rate = 0 if summary.sent_emails == 0 else int(round((reply_total / summary.sent_emails) * 100))
    followup_rate = 0 if summary.sent_emails == 0 else int(round((summary.second_emails / summary.sent_emails) * 100))
    items = [
        ("Total replies", format_number(reply_total)),
        ("Reply rate", f"{reply_rate}%"),
        ("Follow-up rate", f"{followup_rate}%"),
        ("Projected value", format_currency(summary.potential_earnings)),
    ]
    column_width = width / len(items)
    for index, (label, value) in enumerate(items):
        column_x = x + index * column_width
        if index:
            pdf.saveState()
            pdf.setStrokeColor(_rl_color("#edf1f5"))
            pdf.line(column_x, y + 14, column_x, y + height - 14)
            pdf.restoreState()
        _rl_text(pdf, column_x + 16, y + height - 28, label, 8.5, "#667085", bold=True)
        _rl_text(pdf, column_x + 16, y + 20, value, 16, "#111827", bold=True)


def _rl_donut(pdf, x, y, size, values, color_values):
    total = sum(max(0, int(value)) for value in values)
    if total <= 0:
        values = [1]
        color_values = ["#e5e7eb"]
        total = 1
    start = 90
    for value, color in zip(values, color_values):
        extent = 360 * (max(0, int(value)) / total)
        pdf.saveState()
        pdf.setFillColor(_rl_color(color))
        pdf.setStrokeColor(_rl_color(color))
        pdf.wedge(x, y, x + size, y + size, start - extent, start, stroke=0, fill=1)
        pdf.restoreState()
        start -= extent
    inset = size * 0.30
    pdf.saveState()
    pdf.setFillColor(_rl_color("#ffffff"))
    pdf.setStrokeColor(_rl_color("#ffffff"))
    pdf.circle(x + size / 2, y + size / 2, (size / 2) - inset, stroke=0, fill=1)
    pdf.restoreState()


def _rl_legend(pdf, x, y, items):
    cursor = x
    for label, color in items:
        pdf.saveState()
        pdf.setFillColor(_rl_color(color))
        pdf.roundRect(cursor, y + 2, 7, 7, 1.5, stroke=0, fill=1)
        pdf.restoreState()
        _rl_text(pdf, cursor + 11, y, label, 7.5, "#667085")
        cursor += 64


def _rl_logo(pdf, x, y, width, height, logo_path, image_reader):
    if logo_path and os.path.exists(logo_path):
        try:
            image = image_reader(logo_path)
            image_width, image_height = image.getSize()
            scale = min(width / image_width, height / image_height)
            draw_width = image_width * scale
            draw_height = image_height * scale
            pdf.drawImage(
                image,
                x + (width - draw_width) / 2,
                y + (height - draw_height) / 2,
                draw_width,
                draw_height,
                preserveAspectRatio=True,
                mask="auto",
            )
            return
        except Exception:
            pass
    pdf.saveState()
    pdf.setStrokeColor(_rl_color("#98a2b3"))
    pdf.setDash(4, 3)
    pdf.roundRect(x, y, width, height, 8, stroke=1, fill=0)
    pdf.setDash()
    pdf.setFillColor(_rl_color("#667085"))
    pdf.setFont("Helvetica", 11)
    pdf.drawCentredString(x + width / 2, y + height / 2 - 4, "Logo")
    pdf.restoreState()


def _rl_color(value):
    from reportlab.lib.colors import HexColor
    return HexColor(value)


def draw_statistics_report(
    painter,
    rect,
    summary,
    logo_path="",
    title="Outreach Performance",
    date_label="",
    generated_label="",
):
    _ensure_qt()
    summary = summary or StatisticsSummary()
    painter.save()
    _draw_round_rect(painter, rect, QtGui.QColor("#f7f8fb"), QtGui.QColor("#dfe5ee"), 18)

    margin = max(30, int(rect.width() * 0.035))
    content = rect.adjusted(margin, margin, -margin, -margin)
    y = content.top() + 2

    _draw_text(painter, content.left(), y, content.width(), 24, "CLIENT CAMPAIGN REPORT", 10, "#697586", True)
    y += 28
    _draw_text(painter, content.left(), y, content.width() - 190, 40, title, 24, "#111827", True)
    if date_label:
        _draw_text(painter, content.left(), y + 42, content.width() - 190, 22, date_label, 9, "#667085", True)
    _draw_logo(painter, QtCore.QRect(content.right() - 150, y - 5, 138, 54), logo_path)
    _draw_accent_rule(painter, content.left(), y + 72, content.width())
    y += 112

    card_gap = 14
    card_width = int((content.width() - (card_gap * 3)) / 4)
    card_height = 86
    cards = [
        ("Sent", format_number(summary.sent_emails), "#111827"),
        ("Positive", format_number(summary.positive_replies), "#087443"),
        ("Follow-ups", format_number(summary.second_emails), "#111827"),
        ("Potential", format_currency(summary.potential_earnings), "#111827"),
    ]
    for index, (label, value, color) in enumerate(cards):
        x = content.left() + index * (card_width + card_gap)
        _draw_kpi_card(painter, QtCore.QRect(x, y, card_width, card_height), label, value, color)
    y += card_height + 34

    chart_height = min(240, max(190, int(content.height() * 0.28)))
    _draw_chart_panel(
        painter,
        QtCore.QRect(content.left(), y, content.width(), chart_height),
        summary,
    )
    y += chart_height + 28

    insight_height = 138
    _draw_insights(
        painter,
        QtCore.QRect(content.left(), y, content.width(), insight_height),
        summary,
    )
    y += insight_height + 28

    summary_height = 78
    _draw_summary_strip(
        painter,
        QtCore.QRect(content.left(), y, content.width(), summary_height),
        summary,
    )

    if generated_label:
        _draw_text(
            painter,
            content.left(),
            content.bottom() - 18,
            content.width(),
            18,
            generated_label,
            8,
            "#98a2b3",
            False,
            QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter,
        )
    painter.restore()


def _draw_kpi_card(painter, rect, label, value, value_color):
    _draw_round_rect(painter, rect, QtGui.QColor("#ffffff"), QtGui.QColor("#dfe3ea"), 10)
    _draw_text(painter, rect.left() + 16, rect.top() + 17, rect.width() - 26, 22, label, 10, "#667085", True)
    _draw_text(painter, rect.left() + 16, rect.top() + 44, rect.width() - 26, 34, value, 23, value_color, True)


def _draw_chart_panel(painter, rect, summary):
    _draw_round_rect(painter, rect, QtGui.QColor("#f8fbff"), QtGui.QColor("#d5e2ef"), 12)
    _draw_text(
        painter,
        rect.left() + 22,
        rect.top() + 18,
        rect.width() - 44,
        24,
        "Outreach Performance",
        12,
        "#111827",
        True,
    )
    _draw_text(
        painter,
        rect.left() + 22,
        rect.top() + 42,
        rect.width() - 44,
        18,
        "Campaign volume and response movement",
        8,
        "#667085",
        False,
    )
    plot = rect.adjusted(40, 72, -40, -42)
    _draw_grid(painter, plot)
    _draw_axis(painter, plot)

    values = [
        ("Sent", summary.sent_emails, "#028fc3"),
        ("Positive", summary.positive_replies, "#087443"),
        ("Negative", summary.negative_replies, "#c2410c"),
        ("Follow-ups", summary.second_emails, "#475467"),
    ]
    max_value = max([value for _, value, _ in values] + [1])
    bar_width = min(58, max(18, int(plot.width() / 8)))
    spacing = int((plot.width() - bar_width * len(values)) / (len(values) + 1))
    x = plot.left() + spacing
    for label, value, color in values:
        height = max(3 if value else 0, int((plot.height() - 14) * (value / max_value))) if max_value else 0
        if height:
            bar_rect = QtCore.QRect(x, plot.bottom() - height, bar_width, height)
            _draw_round_rect(painter, bar_rect, QtGui.QColor(color), QtGui.QColor(color), 6)
        _draw_text(painter, x - 8, plot.bottom() - height - 22, bar_width + 16, 18, format_number(value), 8, "#111827", True, QtCore.Qt.AlignCenter)
        _draw_text(painter, x - 14, plot.bottom() + 9, bar_width + 28, 18, label, 8, "#667085", False, QtCore.Qt.AlignCenter)
        x += bar_width + spacing


def _draw_insights(painter, rect, summary):
    if rect.height() < 70:
        return
    left = QtCore.QRect(rect.left(), rect.top(), int(rect.width() * 0.48), rect.height())
    right = QtCore.QRect(left.right() + 18, rect.top(), rect.right() - left.right() - 18, rect.height())
    _draw_round_rect(painter, left, QtGui.QColor("#ffffff"), QtGui.QColor("#e5e7eb"), 10)
    _draw_round_rect(painter, right, QtGui.QColor("#ffffff"), QtGui.QColor("#e5e7eb"), 10)

    _draw_text(painter, left.left() + 18, left.top() + 14, left.width() - 36, 24, "Reply Quality", 12, "#111827", True)
    donut_size = max(58, min(74, left.height() - 54))
    left_donut = QtCore.QRect(left.right() - donut_size - 22, left.top() + 38, donut_size, donut_size)
    _draw_donut_chart(
        painter,
        left_donut,
        [
            ("Positive", summary.positive_replies, "#087443"),
            ("Negative", summary.negative_replies, "#c2410c"),
        ],
    )
    positive_pct = int(round(summary.positive_rate * 100))
    text_width = max(110, left_donut.left() - left.left() - 34)
    _draw_text(
        painter,
        left.left() + 18,
        left.top() + 45,
        text_width,
        30,
        "{}% positive".format(positive_pct),
        17,
        "#087443",
        True,
    )
    _draw_text(painter, left.left() + 18, left.top() + 71, text_width, 18, "reply mix", 9, "#087443", True)
    _draw_text(
        painter,
        left.left() + 18,
        left.top() + 91,
        text_width,
        24,
        "{} positive, {} negative".format(format_number(summary.positive_replies), format_number(summary.negative_replies)),
        8,
        "#667085",
        False,
    )
    _draw_legend(
        painter,
        left.left() + 18,
        left.top() + 112,
        [("Positive", "#087443"), ("Negative", "#c2410c")],
    )

    _draw_text(painter, right.left() + 18, right.top() + 14, right.width() - 36, 24, "Email Mix", 12, "#111827", True)
    right_donut = QtCore.QRect(right.right() - donut_size - 22, right.top() + 38, donut_size, donut_size)
    _draw_donut_chart(
        painter,
        right_donut,
        [
            ("Sent", summary.sent_emails, "#028fc3"),
            ("Follow-ups", summary.second_emails, "#475467"),
            ("Positive", summary.positive_replies, "#087443"),
        ],
    )
    text_width = max(110, right_donut.left() - right.left() - 34)
    _draw_text(
        painter,
        right.left() + 18,
        right.top() + 45,
        text_width,
        32,
        format_currency(summary.potential_earnings),
        18,
        "#111827",
        True,
    )
    _draw_text(
        painter,
        right.left() + 18,
        right.top() + 82,
        text_width,
        24,
        "Potential from interested replies",
        8,
        "#667085",
        False,
    )
    _draw_legend(
        painter,
        right.left() + 18,
        right.top() + 112,
        [("Sent", "#028fc3"), ("Follow-ups", "#475467"), ("Positive", "#087443")],
    )


def _draw_summary_strip(painter, rect, summary):
    _draw_round_rect(painter, rect, QtGui.QColor("#ffffff"), QtGui.QColor("#e5e7eb"), 10)
    reply_total = summary.total_replies
    reply_rate = 0 if summary.sent_emails == 0 else int(round((reply_total / summary.sent_emails) * 100))
    followup_rate = 0 if summary.sent_emails == 0 else int(round((summary.second_emails / summary.sent_emails) * 100))
    items = [
        ("Total replies", format_number(reply_total)),
        ("Reply rate", "{}%".format(reply_rate)),
        ("Follow-up rate", "{}%".format(followup_rate)),
        ("Projected value", format_currency(summary.potential_earnings)),
    ]
    column_width = int(rect.width() / len(items))
    painter.save()
    for index, (label, value) in enumerate(items):
        x = rect.left() + index * column_width
        if index:
            painter.setPen(QtGui.QPen(QtGui.QColor("#edf1f5"), 1))
            painter.drawLine(x, rect.top() + 16, x, rect.bottom() - 16)
        _draw_text(painter, x + 18, rect.top() + 17, column_width - 36, 20, label, 8, "#667085", True)
        _draw_text(painter, x + 18, rect.top() + 41, column_width - 36, 26, value, 15, "#111827", True)
    painter.restore()


def _draw_donut_chart(painter, rect, values):
    total = sum(max(0, int(value)) for _, value, _ in values)
    painter.save()
    if total <= 0:
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor("#e5e7eb"))
        painter.drawEllipse(rect)
    else:
        start_angle = 90 * 16
        for _, value, color in values:
            span = int(round((max(0, int(value)) / total) * 360 * 16))
            if span == 0:
                continue
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(color))
            painter.drawPie(rect, start_angle, -span)
            start_angle -= span
    inner_margin = max(12, int(rect.width() * 0.28))
    painter.setBrush(QtGui.QColor("#ffffff"))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawEllipse(rect.adjusted(inner_margin, inner_margin, -inner_margin, -inner_margin))
    painter.restore()


def _draw_legend(painter, x, y, items):
    painter.save()
    cursor_x = x
    for label, color in items:
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(QtGui.QColor(color))
        painter.drawRoundedRect(QtCore.QRect(cursor_x, y + 5, 9, 9), 2, 2)
        _draw_text(painter, cursor_x + 13, y, 78, 18, label, 8, "#667085", False)
        cursor_x += 92
    painter.restore()


def _draw_logo(painter, rect, logo_path):
    if logo_path and os.path.exists(logo_path):
        pixmap = QtGui.QPixmap(logo_path)
        if not pixmap.isNull():
            scaled = pixmap.scaled(rect.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            x = rect.left() + int((rect.width() - scaled.width()) / 2)
            y = rect.top() + int((rect.height() - scaled.height()) / 2)
            painter.drawPixmap(x, y, scaled)
            return
    pen = QtGui.QPen(QtGui.QColor("#98a2b3"))
    pen.setStyle(QtCore.Qt.DashLine)
    pen.setWidth(2)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.NoBrush)
    painter.drawRoundedRect(rect, 8, 8)
    _draw_text(painter, rect.left(), rect.top(), rect.width(), rect.height(), "Logo", 11, "#667085", False, QtCore.Qt.AlignCenter)


def _draw_axis(painter, rect):
    painter.save()
    pen = QtGui.QPen(QtGui.QColor("#028fc3"))
    pen.setWidth(2)
    painter.setPen(pen)
    painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
    painter.drawLine(rect.left(), rect.top(), rect.left(), rect.bottom())
    painter.restore()


def _draw_grid(painter, rect):
    painter.save()
    pen = QtGui.QPen(QtGui.QColor("#d8e6f2"))
    pen.setWidth(1)
    painter.setPen(pen)
    for index in range(1, 4):
        y = rect.top() + int(rect.height() * index / 4)
        painter.drawLine(rect.left(), y, rect.right(), y)
    painter.restore()


def _draw_accent_rule(painter, x, y, width):
    painter.save()
    pen = QtGui.QPen(QtGui.QColor("#028fc3"))
    pen.setWidth(2)
    painter.setPen(pen)
    painter.drawLine(x, y, x + width, y)
    pen.setColor(QtGui.QColor("#087443"))
    painter.setPen(pen)
    painter.drawLine(x + int(width * 0.45), y, x + int(width * 0.62), y)
    pen.setColor(QtGui.QColor("#c2410c"))
    painter.setPen(pen)
    painter.drawLine(x + int(width * 0.62), y, x + int(width * 0.75), y)
    painter.restore()


def _draw_round_rect(painter, rect, fill, stroke, radius):
    painter.save()
    painter.setPen(QtGui.QPen(stroke, 1))
    painter.setBrush(fill)
    painter.drawRoundedRect(rect, radius, radius)
    painter.restore()


def _draw_text(painter, x, y, width, height, text, size, color, bold=False, flags=None):
    painter.save()
    font = QtGui.QFont("Arial", size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QtGui.QColor(color))
    if flags is None:
        flags = QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter
    painter.drawText(QtCore.QRect(int(x), int(y), int(width), int(height)), flags, str(text))
    painter.restore()
