from src.config import settings
from src.security import RateLimiter, limit_by_ip

join_limiter = RateLimiter(limit=settings.waitlist_joins_per_ip_per_hour, window_seconds=3600)
limit_joins = limit_by_ip(join_limiter)
