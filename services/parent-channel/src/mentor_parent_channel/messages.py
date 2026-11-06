"""Every Vietnamese text a parent receives from the Zalo bot.

Zalo Bot terms (https://bot.zapps.me/docs/terms/) require: telling users before they interact that the bot
is an automated system, saying whether user data is collected/processed, and labelling AI-generated
content. Plan 7.6 / 8.3 fix what parents receive and the crisis wording.
"""

from mentor_schemas.reports import AI_DISCLAIMER

CONSENT_KEYWORD = "ĐỒNG Ý"
AI_LABEL = "[Nội dung do AI tạo]"

# Plan 7.6, tier 3. Fixed text: no category, no conversation content, no details.
CRISIS_ALERT = "Hệ thống ghi nhận con cần được hỗ trợ. Phụ huynh vui lòng liên hệ với con, hoặc gọi Tổng đài 111."


def consent_request(bot_name: str) -> str:
    return (
        f"Xin chào phụ huynh. Đây là {bot_name}, một hệ thống tự động sử dụng trí tuệ nhân tạo (AI), "
        "không phải người thật. Bot chỉ gửi thông báo và không trả lời câu hỏi.\n\n"
        "Nếu phụ huynh đồng ý liên kết, bot sẽ gửi:\n"
        "• Báo cáo học tập 2 tuần một lần: tiến độ mục tiêu, mức độ đều đặn khi học và xu hướng tiến bộ "
        "theo từng chủ đề. Báo cáo do AI tạo, không có điểm từng bài kiểm tra và không có nội dung trò "
        "chuyện của con.\n"
        "• Cảnh báo khẩn cấp ngay khi hệ thống ghi nhận con có thể gặp nguy hiểm.\n\n"
        "Về dữ liệu: hệ thống thu thập và xử lý dữ liệu học tập của con, cùng mã tài khoản Zalo và tên "
        "hiển thị của phụ huynh, để tạo và gửi các thông báo trên. Dữ liệu được xử lý bằng mô hình AI và có "
        "thể được xử lý trên máy chủ đặt ngoài Việt Nam. Con chỉ dùng được mentor sau khi phụ huynh đồng ý.\n\n"
        f"Để đồng ý, phụ huynh vui lòng trả lời: {CONSENT_KEYWORD}"
    )


def confirmation(bot_name: str) -> str:
    return (
        "Cảm ơn phụ huynh. Liên kết đã hoàn tất và con có thể bắt đầu sử dụng mentor. "
        f"{bot_name} sẽ gửi báo cáo học tập 2 tuần một lần và cảnh báo khi cần thiết. "
        "Đây là hệ thống tự động, bot không trả lời tin nhắn."
    )


def help_unlinked(bot_name: str) -> str:
    return (
        f"Đây là {bot_name}, hệ thống tự động sử dụng AI để gửi báo cáo học tập cho phụ huynh. "
        "Để liên kết, phụ huynh vui lòng gửi mã 6 chữ số hiển thị trong ứng dụng của con."
    )


def help_awaiting_consent() -> str:
    return f"Để hoàn tất liên kết, phụ huynh vui lòng trả lời: {CONSENT_KEYWORD}"


def help_verified(bot_name: str) -> str:
    return (
        f"Tài khoản đã được liên kết. {bot_name} là hệ thống tự động, chỉ gửi báo cáo học tập 2 tuần một lần "
        "và cảnh báo khi cần thiết, không trả lời tin nhắn."
    )


def invalid_code() -> str:
    return "Mã liên kết không đúng. Phụ huynh vui lòng kiểm tra lại mã 6 chữ số trong ứng dụng của con."


def expired_code() -> str:
    return "Mã liên kết đã hết hạn. Phụ huynh vui lòng nhờ con tạo mã mới trong ứng dụng rồi gửi lại."


def too_many_attempts() -> str:
    return "Phụ huynh đã nhập sai mã quá nhiều lần. Vui lòng thử lại sau 1 giờ."


def already_linked_other() -> str:
    return (
        "Tài khoản Zalo này đã được liên kết với một học sinh khác. Hiện mỗi tài khoản chỉ liên kết được một học sinh."
    )


def report(bot_name: str, body: str, *, append_disclaimer: bool = True) -> str:
    """Wrap a plain-text report with the AI label; add the plan 7.6 disclaimer only when asked
    (the caller passes False when the report body already contains it)."""
    text = f"{AI_LABEL} Báo cáo học tập định kỳ từ {bot_name}\n\n{body.strip()}"
    return f"{text}\n\n{AI_DISCLAIMER}" if append_disclaimer else text
