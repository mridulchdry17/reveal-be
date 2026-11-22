from enum import StrEnum
from zoneinfo import ZoneInfo

DROP_SIZE = 5
# A new drop opens at 9 PM college time and stays open until the next one.
DROP_HOUR = 21
COLLEGE_TZ = ZoneInfo("Asia/Kolkata")
# Someone you didn't answer can come back in a later drop after this many days.
RESHOW_AFTER_DAYS = 14


class Decision(StrEnum):
    LIKED = "liked"
    PASSED = "passed"
